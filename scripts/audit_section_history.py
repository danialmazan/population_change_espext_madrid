"""Compare pinned official change records with each endpoint's raw membership."""

import hashlib
import json
from pathlib import Path
from madrid_demography.acquisition import read_lock, digest
from madrid_demography.parent_audit import read_membership
from madrid_demography.section_history import read_registry, compare_registry


def main():
    sources = {s["id"]: s for s in read_lock("sources.lock.yml")["sources"]}

    def pinned(sid):
        s = sources[sid]
        p = Path("data/raw") / sid / s["sha256"]
        if digest(p) != s["sha256"] or p.stat().st_size != s["bytes"]:
            raise ValueError("Changed registry/population source")
        return p

    sid = "municipal_section_history"
    records, metadata = read_registry(pinned(sid))
    comparisons = []
    for year in (2015, 2025):
        source = sources[f"padron_january_{year}"]
        membership, _, _, _ = read_membership(pinned(source["id"]), source)
        comparisons.append(compare_registry(records, membership, f"{year}-01-01"))
    report = dict(
        production_ready=False,
        source_id=sid,
        source_sha256=sources[sid]["sha256"],
        metadata=metadata,
        date_errors=[
            r
            for r in records
            if any(
                r[k]["status"] == "invalid_date_year_only"
                for k in ("created", "closed", "modified")
            )
        ],
        comparisons=comparisons,
        documented_parent_reassignments=[r for r in records if r["previous_parent"]],
        interpretation="Official 1988–2024 change records corroborate membership; year-bracketing preserves invalid dates and cannot determine a date within the erroneous year. Registry comparisons use created <= endpoint < closed; carry-forward into January 2025 remains provisional. No historical boundary geometry is approved by this registry.",
    )
    boundary_path = Path("docs/audit/boundary-review.json")
    boundary = json.loads(boundary_path.read_text())
    for year in (2015, 2025):
        sid = f"padron_january_{year}"
        if boundary["source_hashes"][sid] != sources[sid]["sha256"]:
            raise ValueError("Boundary review population source changed")
    issues = {
        int(c["endpoint"][:4]): {r["section_id"] for r in c["differences"]}
        for c in comparisons
    }
    unchanged = [
        c
        for c in boundary["components"]
        if c["classification"] == "unchanged" and not c["stable_raw_parent_code"]
    ]
    corroborated = [
        c["zone_id"]
        for c in unchanged
        if not (set(c["old_ids"]) & issues[2015] or set(c["new_ids"]) & issues[2025])
    ]
    report["boundary_review_sha256"] = hashlib.sha256(
        boundary_path.read_bytes()
    ).hexdigest()
    report["unchanged_geometry_parent_exception_corroboration"] = dict(
        total=len(unchanged),
        fully_matching_registry_count=len(corroborated),
        matching_zone_ids=corroborated,
        remaining_zone_ids=[
            c["zone_id"] for c in unchanged if c["zone_id"] not in corroborated
        ],
    )
    Path("docs/audit/section-history.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    )
    print(
        json.dumps(
            {
                **report,
                "date_errors": len(report["date_errors"]),
                "documented_parent_reassignments": len(
                    report["documented_parent_reassignments"]
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
