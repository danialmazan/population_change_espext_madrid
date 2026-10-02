"""Reproduce pipeline boundary classification and raw-parent exception accounting."""

import csv
import json
from collections import Counter
from pathlib import Path
from madrid_demography.acquisition import read_lock, digest
from madrid_demography.boundary_audit import read_sections
from madrid_demography.geography import overlay, validate_crosswalk
from madrid_demography.parent_audit import read_membership, assess_parents


def main():
    sources = {s["id"]: s for s in read_lock("sources.lock.yml")["sources"]}
    geometries, memberships, populations, metadata, missing, by_parent = (
        {},
        {},
        {},
        {},
        {},
        {},
    )
    hashes = {}
    for year in (2015, 2025):
        for prefix in ("sections", "padron_january"):
            source = sources[f"{prefix}_{year}"]
            path = Path("data/raw") / source["id"] / source["sha256"]
            if (
                digest(path) != source["sha256"]
                or path.stat().st_size != source["bytes"]
            ):
                raise ValueError("Changed or missing geometry/population source")
            hashes[source["id"]] = source["sha256"]
            if prefix == "sections":
                geometries[year], metadata[year] = read_sections(path)
                if metadata[year]["invalid_or_empty_ids"]:
                    raise ValueError("Geometry repair requires separate evidence")
            else:
                memberships[year], populations[year], by_parent[year], missing[year] = (
                    read_membership(path, source)
                )
    result = overlay(geometries[2015], geometries[2025])
    for vintage, year in (("old", 2015), ("new", 2025)):
        validate_crosswalk(
            [r for r in result["crosswalk"] if r["vintage"] == vintage],
            set(geometries[year]),
        )
    old_audit = json.loads(Path("docs/audit/boundaries.json").read_text())
    old_groups = {
        (tuple(c["old_ids"]), tuple(c["new_ids"])) for c in old_audit["components"]
    }
    new_groups = {
        (tuple(c["old_ids"]), tuple(c["new_ids"])) for c in result["components"]
    }
    records = []
    for component in result["components"]:
        record = {
            **component,
            **assess_parents(
                component["old_ids"],
                component["new_ids"],
                memberships[2015],
                memberships[2025],
            ),
        }
        for year, side in ((2015, "old"), (2025, "new")):
            ids = component[f"{side}_ids"]
            record[f"{side}_known_population"] = sum(
                populations[year].get(g, 0) for g in ids
            )
            record[f"{side}_land_area_m2"] = sum(geometries[year][g].area for g in ids)
        record["review_status"] = "geometry_metrics_checked_parent_evidence_pending"
        records.append(record)
    accounting = {}
    for year, side in ((2015, "old"), (2025, "new")):
        total = sum(populations[year].values()) + missing[year]
        mapped = sum(c[f"{side}_known_population"] for c in records)
        exceptions = {
            gid: count
            for gid, count in sorted(populations[year].items())
            if gid not in geometries[year]
        }
        if mapped + sum(exceptions.values()) + missing[year] != total:
            raise ValueError("Boundary component population accounting failed")
        parent_stable = sum(
            c[f"{side}_known_population"]
            for c in records
            if c["stable_raw_parent_code"]
        )
        accounting[year] = dict(
            known_total=total,
            mapped_known_population=mapped,
            raw_parent_stable_known_population=parent_stable,
            raw_parent_stable_known_population_share=parent_stable / total,
            geometry_missing_known_population=exceptions,
            section_missing_known_population=missing[year],
            by_boundary_class={
                kind: sum(
                    c[f"{side}_known_population"]
                    for c in records
                    if c["classification"] == kind
                )
                for kind in sorted({c["classification"] for c in records})
            },
        )
    report = dict(
        production_ready=False,
        source_hashes=hashes,
        geometry_metadata=metadata,
        overlay_tolerance=0.001,
        material_overlap_ratio=1e-6,
        previous_candidate_component_sets_identical=old_groups == new_groups,
        component_counts=dict(Counter(c["classification"] for c in records)),
        parent_status_counts=dict(Counter(c["raw_parent_status"] for c in records)),
        geometry_unchanged_parent_exception_count=sum(
            c["classification"] == "unchanged" and not c["stable_raw_parent_code"]
            for c in records
        ),
        cross_district_component_count=sum(
            not c["stable_raw_district_code"] for c in records
        ),
        maximum_symmetric_difference_ratio=max(
            c["symmetric_difference_ratio"] for c in records
        ),
        old_topology=result["old_topology"],
        new_topology=result["new_topology"],
        population_accounting=accounting,
        ambiguous_section_memberships={
            year: {
                gid: [
                    dict(
                        district=d,
                        barrio=b,
                        known_population=by_parent[year][(gid, (d, b))],
                    )
                    for d, b in sorted(parents)
                ]
                for gid, parents in memberships[year].items()
                if len(parents) > 1
            }
            for year in (2015, 2025)
        },
        release_blockers=[
            "Independent historical barrio/district boundaries are not acquired or verified",
            "Changed components require documented analytical review",
            "Raw missing/exceptional geography remains outside section results",
        ],
        components=records,
    )
    Path("docs/audit/boundary-review.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    # Deliberately use audit-only column names, rather than model crosswalk contracts.
    path = Path("docs/audit/boundary-review.csv")
    fields = [
        "candidate_zone_id",
        "boundary_class",
        "raw_parent_status",
        "old_sections",
        "new_sections",
        "old_parent_codes",
        "new_parent_codes",
        "old_known_population",
        "new_known_population",
        "symmetric_difference_ratio",
        "review_status",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for c in records:
            writer.writerow(
                dict(
                    candidate_zone_id=c["zone_id"],
                    boundary_class=c["classification"],
                    raw_parent_status=c["raw_parent_status"],
                    old_sections="|".join(c["old_ids"]),
                    new_sections="|".join(c["new_ids"]),
                    old_parent_codes="|".join(b for d, b in c["old_parents"]),
                    new_parent_codes="|".join(b for d, b in c["new_parents"]),
                    old_known_population=c["old_known_population"],
                    new_known_population=c["new_known_population"],
                    symmetric_difference_ratio=c["symmetric_difference_ratio"],
                    review_status=c["review_status"],
                )
            )
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in ("components", "old_topology", "new_topology")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
