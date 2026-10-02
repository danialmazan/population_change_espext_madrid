"""Summarise acquired snapshots and explicitly keep production gates closed."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .acquire import load_manifest
from .profile import latest_receipt, profile_mortality


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("sources.lock.yml"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--report-dir", type=Path, default=Path("docs/audit"))
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    observations, paths = [], {}
    for source in manifest["sources"]:
        receipt = latest_receipt(args.raw_dir, source)
        if receipt is None:
            receipt = {
                "source_id": source["id"],
                "status": "failed",
                "error": "not acquired",
            }
        receipt = dict(receipt)
        if receipt["status"] != "failed":
            path = Path(receipt["path"])
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            if checksum != receipt["sha256"] or source.get("sha256") not in (
                None,
                checksum,
            ):
                receipt.update(
                    status="failed",
                    error="stored bytes differ from receipt or manifest",
                )
            else:
                paths[source["id"]] = path
                receipt["pin_status_at_report"] = (
                    "pinned" if source.get("sha256") else "unreviewed"
                )
        observations.append(receipt)
    args.report_dir.mkdir(parents=True, exist_ok=True)

    def write(name, value):
        (args.report_dir / name).write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + "\n"
        )

    write(
        "acquisition.json",
        {
            "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
            "dataset_kind": "audit_only",
            "production_ready": False,
            "sources": observations,
        },
    )
    mortality = {}
    for table, series, region in (
        ("mortality_table", "mortality_series", "Madrid, Comunidad de"),
        ("mortality_national_table", "mortality_national_series", None),
    ):
        if table in paths and series in paths:
            mortality[table] = profile_mortality(
                paths[table], paths[series], region=region
            )
    write("mortality.json", mortality)
    sources = {s["id"]: s for s in manifest["sources"]}
    reconciliation_path = args.report_dir / "reconciliation.json"
    reconciliation = (
        json.loads(reconciliation_path.read_text())
        if reconciliation_path.exists()
        else None
    )
    if reconciliation and (
        reconciliation.get("comparison_sha256")
        != sources.get("ine_approved_population", {}).get("sha256")
        or any(
            r["source_sha256"] != sources[r["source_id"]]["sha256"]
            for r in reconciliation["comparisons"]
            + reconciliation.get("municipal_revised_comparisons", [])
        )
    ):
        raise ValueError("reconciliation report is stale relative to the manifest")
    normalisation_path = args.report_dir / "normalisation.json"
    normalisation = (
        json.loads(normalisation_path.read_text())
        if normalisation_path.exists()
        else None
    )
    if normalisation and (
        normalisation["config_sha256"]
        != hashlib.sha256(Path("config/analysis.json").read_bytes()).hexdigest()
        or normalisation["aliases_sha256"]
        != hashlib.sha256(Path("config/schema_aliases.json").read_bytes()).hexdigest()
        or any(
            r["source_sha256"] != sources[r["source_id"]]["sha256"]
            for r in normalisation["population"]
        )
    ):
        raise ValueError(
            "normalisation report is stale relative to the configuration or manifest"
        )
    gates = [
        {
            "gate": "monthly_reference_dates",
            "status": "documented" if "padron_documentation" in paths else "pending",
            "evidence": "padron_documentation: each monthly file refers to day 1; release dates are distinct",
        },
        {
            "gate": "independent_population_totals",
            "status": "compared_unresolved" if reconciliation else "pending",
            "reason": "Independent INE legal and annual revised municipal totals acquired. Section differences add to city discrepancies and No consta is accounted for; monthly-versus-revised source policy and blank interpretation remain unresolved.",
        },
        {
            "gate": "padron_schema_contracts",
            "status": "implemented_with_unresolved_counts"
            if normalisation
            else "requires_review",
            "reason": "Versioned aliases and conservation checks implemented. Blank counts stay null, terminal ages stay separate, missing sections and split barrio memberships are preserved.",
        },
        {
            "gate": "mortality_method",
            "status": "configured_national_single_age"
            if normalisation
            else "requires_review",
            "reason": "Spain single-age qx configured with explicit per-thousand conversion and ages 10–99 counterfactual scope. National mortality caveat and pending regional sensitivity recorded.",
        },
        {
            "gate": "geographic_comparability",
            "status": "requires_review",
            "reason": "Review provisional components and source/code exceptions; audit historical barrio/district boundaries and parent containment.",
        },
    ]
    write(
        "feasibility.json",
        {
            "production_ready": False,
            "completed_scope": "source acquisition, preliminary feasibility audit, independent endpoint comparison and audit normalisation"
            if normalisation
            else "source acquisition and preliminary feasibility audit",
            "sources_acquired": len(paths),
            "sources_required": len(sources),
            "gates": gates,
        },
    )
    print(f"{len(paths)}/{len(sources)} snapshots verified; production_ready=false")
    return int(len(paths) != len(sources))


if __name__ == "__main__":
    raise SystemExit(main())
