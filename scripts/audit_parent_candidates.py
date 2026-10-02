"""Inspect discovered parent layers without approving uncertain endpoint dates."""

import hashlib
import json
from collections import Counter
from pathlib import Path
from madrid_demography.acquisition import read_lock, digest
from madrid_demography.boundary_audit import read_sections
from madrid_demography.parent_audit import read_membership
from madrid_demography.parent_geometry import (
    read_parent_layer,
    containment_review,
    require_parent_vintage,
)
from madrid_demography.io import ContractError


def main():
    sources = {s["id"]: s for s in read_lock("sources.lock.yml")["sources"]}
    config_path = Path("config/parent-candidates.json")
    config = json.loads(config_path.read_text())
    sections, memberships, population = {}, {}, {}

    def pinned(sid):
        source = sources[sid]
        path = Path("data/raw") / sid / source["sha256"]
        if digest(path) != source["sha256"] or path.stat().st_size != source["bytes"]:
            raise ContractError("Changed or missing pinned source")
        return path

    for year in (2015, 2025):
        sections[year], _ = read_sections(pinned(f"sections_{year}"))
        memberships[year], population[year], _, _ = read_membership(
            pinned(f"padron_january_{year}"), sources[f"padron_january_{year}"]
        )
    reports = []
    for c in config["candidates"]:
        if c["source_sha256"] != sources[c["source_id"]]["sha256"]:
            raise ContractError("Parent candidate and manifest hashes differ")
        parents, metadata = read_parent_layer(pinned(c["source_id"]), c)
        year = int(c["target_date"][:4])
        records = containment_review(
            sections[year], parents, memberships[year], population[year], c["level"]
        )
        try:
            require_parent_vintage(c, c["target_date"])
            usable = True
        except ContractError:
            usable = False
        counts = Counter(r["status"] for r in records)
        populations = {
            status: sum(r["known_population"] for r in records if r["status"] == status)
            for status in sorted(counts)
        }
        reports.append(
            dict(
                candidate_id=c["id"],
                source_id=c["source_id"],
                source_sha256=c["source_sha256"],
                level=c["level"],
                target_date=c["target_date"],
                temporal_validity_verified=usable,
                temporal_reason=c["temporal_reason"],
                metadata=metadata,
                containment_tolerance=0.001,
                status_counts=dict(counts),
                known_population_by_containment_status=populations,
                exceptions=[
                    r
                    for r in records
                    if r["status"] != "contained_candidate"
                    or r.get("ambiguous_raw_parent")
                ],
                maximum_outside_area_ratio=max(
                    (r.get("outside_area_ratio", 0) for r in records), default=0
                ),
            )
        )
    report = dict(
        production_ready=False,
        manifest_sha256=hashlib.sha256(
            Path("sources.lock.yml").read_bytes()
        ).hexdigest(),
        config_sha256=hashlib.sha256(config_path.read_bytes()).hexdigest(),
        independent_parent_sources_acquired=True,
        temporally_verified_endpoint_parent_layers=sum(
            r["temporal_validity_verified"] for r in reports
        ),
        candidates=reports,
        next_requirement="Confirm January endpoint validity with official dated boundaries/change records before approving parent assignments",
    )
    Path("docs/audit/parent-candidates.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    )
    print(
        json.dumps(
            {
                **report,
                "candidates": [
                    {k: v for k, v in r.items() if k not in ("metadata", "exceptions")}
                    for r in reports
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
