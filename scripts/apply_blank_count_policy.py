"""Validate conditional evidence and export a labelled research candidate."""

import hashlib
import json
from pathlib import Path
from madrid_demography.acquisition import read_lock
from madrid_demography.count_policy import validate_policy, export_candidate


def main():
    policy_path = Path("config/blank-count-policy.json")
    policy = json.loads(policy_path.read_text())
    source = next(
        s
        for s in read_lock("sources.lock.yml")["sources"]
        if s["id"] == policy["source_id"]
    )
    stats = validate_policy(
        policy, source, Path("data/raw") / source["id"] / source["sha256"]
    )
    normalization = json.loads(Path("docs/audit/normalisation.json").read_text())
    audit = next(
        p for p in normalization["population"] if p["source_id"] == policy["source_id"]
    )
    candidate = export_candidate(
        audit["output_path"],
        audit["output_sha256"],
        "data/normalised/padron_2015_monthly_candidate.csv",
        policy,
        stats["inferred_zero_cells"],
    )
    report = dict(
        policy_id=policy["id"],
        policy_sha256=hashlib.sha256(policy_path.read_bytes()).hexdigest(),
        production_ready=False,
        raw_blanks_retained=audit["unknown_count_cells"],
        out_of_scope_blanks=audit["unknown_count_cells"] - stats["inferred_zero_cells"],
        **stats,
        candidate=candidate,
        remaining_gates=[
            "Source universe and policy review",
            "Monthly versus annual revision policy",
            "Boundary and historical parent review",
            "Independent survival, sensitivity and licensing reviews",
        ],
    )
    Path("docs/audit/blank-count-policy.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
