"""Create provenance-preserving long-form inputs; unresolved counts remain null."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from .acquire import load_manifest
from .profile import profile_mortality
from .reconcile import verified_path


COUNT_COLUMNS = {
    "ESPANOLESHOMBRES": ("male", "ESP"),
    "ESPANOLESMUJERES": ("female", "ESP"),
    "EXTRANJEROSHOMBRES": ("male", "EXT"),
    "EXTRANJEROSMUJERES": ("female", "EXT"),
}


def age_fields(label: str, year: int, config: dict) -> tuple[int | None, str, str]:
    if label == "100 o +":
        return None, "open_100_plus", "excluded_terminal"
    try:
        age = int(label)
    except ValueError:
        return None, "unknown", "excluded_invalid_age"
    if not 0 <= age <= 130:
        return age, "outside_contract", "excluded_invalid_age"
    interval = int(config["end_date"][:4]) - int(config["start_date"][:4])
    endpoint_age = age + interval if year == int(config["start_date"][:4]) else age
    if endpoint_age > config["cohort_endpoint_age_max"]:
        return age, "single", "excluded_terminal"
    if endpoint_age < config["cohort_endpoint_age_min"]:
        return age, "single", "observed_born_during_interval"
    return age, "single", "eligible"


def normalise_population(
    path: Path,
    source: dict,
    contract: dict,
    config: dict,
    output: Path,
    geometry_ids: set[str],
) -> dict:
    fields = [
        "reference_date",
        "source_geography_id",
        "geography_status",
        "district_code",
        "barrio_code",
        "age",
        "age_label",
        "age_kind",
        "sex",
        "nationality",
        "population",
        "population_status",
        "cohort_status",
        "has_geometry",
        "source_file_id",
        "source_sha256",
        "schema_version",
        "raw_row_number",
    ]
    stats, category_totals, blank_columns = Counter(), Counter(), Counter()
    stats.update(
        long_rows=0,
        unknown_count_cells=0,
        known_population_sum=0,
        known_population_without_geometry=0,
    )
    seen, parents = set(), {}
    year = int(source["reference_date"][:4])
    output.parent.mkdir(parents=True, exist_ok=True)
    with (
        path.open(encoding=contract["encoding"], newline="") as handle,
        output.open("w", encoding="utf-8", newline="") as out,
    ):
        reader = csv.DictReader(handle, delimiter=contract["delimiter"])
        if set(reader.fieldnames or []) != set(contract["columns"]):
            raise ValueError("raw header differs from versioned alias contract")
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader()
        for line, raw in enumerate(reader, 2):
            if None in raw or any(v is None for v in raw.values()):
                raise ValueError(f"malformed row {line}")
            row = {contract["columns"][k]: v.strip() for k, v in raw.items()}
            for date_column in ("FX_DATOS_INI", "FX_DATOS_FIN"):
                if date_column in row and row[date_column].replace("-", "") != source[
                    "reference_date"
                ].replace("-", ""):
                    raise ValueError(f"reference date mismatch at row {line}")
            district, barrio = int(row["COD_DISTRITO"]), int(row["COD_DIST_BARRIO"])
            section = int(row["COD_DIST_SECCION"]) if row["COD_DIST_SECCION"] else None
            if not 1 <= district <= 21 or (
                section is not None and section // 1000 != district
            ):
                raise ValueError(f"inconsistent district/section at row {line}")
            geography_id = (
                f"28079{district:02d}{section % 1000:03d}"
                if section is not None
                else ""
            )
            label = row["COD_EDAD_INT"]
            key = (geography_id, district, barrio, label)
            if key in seen:
                raise ValueError(f"duplicate full-grain source row {line}: {key}")
            seen.add(key)
            if geography_id:
                parents.setdefault(geography_id, set()).add(barrio)
            age, kind, cohort = age_fields(label, year, config)
            for column, (sex, nationality) in COUNT_COLUMNS.items():
                value = row[column]
                count = None if value == "" else int(value)
                if count is not None and count < 0:
                    raise ValueError(f"negative population at row {line}")
                stats["long_rows"] += 1
                if count is None:
                    stats["unknown_count_cells"] += 1
                    blank_columns[column] += 1
                else:
                    stats["known_population_sum"] += count
                    category_totals[cohort] += count
                    if geography_id not in geometry_ids:
                        stats["known_population_without_geometry"] += count
                writer.writerow(
                    dict(
                        zip(
                            fields,
                            [
                                source["reference_date"],
                                geography_id,
                                "coded" if section is not None else "missing_section",
                                f"{district:02d}",
                                f"{barrio:04d}",
                                age,
                                label,
                                kind,
                                sex,
                                nationality,
                                count,
                                "unknown_blank" if count is None else "observed",
                                cohort,
                                int(geography_id in geometry_ids),
                                source["id"],
                                source["sha256"],
                                contract["schema_version"],
                                line,
                            ],
                        )
                    )
                )
    return {
        "source_id": source["id"],
        "source_sha256": source["sha256"],
        **stats,
        "unknown_by_count_column": dict(blank_columns),
        "known_population_by_cohort_status": dict(category_totals),
        "sections_with_multiple_barrios": {
            k: sorted(v) for k, v in parents.items() if len(v) > 1
        },
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "output_path": str(output),
        "production_ready": False,
    }


def normalise_mortality(path: Path, output: Path, config: dict) -> dict:
    cells = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter=";"):
            if row["Funciones"] != config["mortality_measure"] or row["Sexo"] not in (
                "Hombres",
                "Mujeres",
            ):
                continue
            year = int(row["Periodo"])
            match = re.fullmatch(r"(\d+) años?", row["Edad"])
            if not match or not int(config["start_date"][:4]) <= year < int(
                config["end_date"][:4]
            ):
                continue
            age = int(match[1])
            if age > 99:
                continue
            sex = {"Hombres": "male", "Mujeres": "female"}[row["Sexo"]]
            qx = (
                float(row["Total"].replace(".", "").replace(",", "."))
                / config["mortality_unit_divisor"]
            )
            key = (year, age, sex)
            if key in cells or not 0 <= qx <= 1:
                raise ValueError(f"invalid or duplicate mortality cell {key}")
            cells[key] = qx
    required = {
        (y, a, s)
        for y in range(int(config["start_date"][:4]), int(config["end_date"][:4]))
        for a in range(100)
        for s in ("male", "female")
    }
    if set(cells) != required:
        raise ValueError("incomplete single-age mortality coverage")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["year", "age", "sex", "qx"])
        for (year, age, sex), qx in sorted(cells.items()):
            writer.writerow([year, age, sex, qx])
    return {
        "region": config["mortality_region"],
        "cells": len(cells),
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "output_path": str(output),
        "unit_conversion": "Riesgo de muerte / 1000",
        "terminal_group_not_expanded": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("sources.lock.yml"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/normalised"))
    parser.add_argument(
        "--report", type=Path, default=Path("docs/audit/normalisation.json")
    )
    args = parser.parse_args()
    config_path, aliases_path = (
        Path("config/analysis.json"),
        Path("config/schema_aliases.json"),
    )
    config, contracts = (
        json.loads(config_path.read_text()),
        json.loads(aliases_path.read_text()),
    )
    if (config["start_date"], config["end_date"]) != ("2015-01-01", "2025-01-01"):
        raise ValueError(
            "this normalisation command currently supports the audited 2015/2025 endpoints"
        )
    if (
        config["blank_count_policy"] != "unknown_null"
        or config["mortality_region"] != "Spain"
        or config["mortality_unit_divisor"] != 1000
    ):
        raise ValueError("unsupported count or mortality policy")
    sources = {s["id"]: s for s in load_manifest(args.manifest)["sources"]}
    boundaries = json.loads(Path("docs/audit/boundaries.json").read_text())
    profiles = {
        p["source_id"]: p
        for p in json.loads(Path("docs/audit/padron_profiles.json").read_text())[
            "profiles"
        ]
    }
    populations = []
    for year, side in ((2015, "old_ids"), (2025, "new_ids")):
        source = sources[f"padron_january_{year}"]
        ids = {k for c in boundaries["components"] for k in c[side]}
        report = normalise_population(
            verified_path(source, args.raw_dir),
            source,
            contracts[source["id"]],
            config,
            args.output_dir / f"padron_{source['reference_date']}.csv",
            ids,
        )
        if (
            report["known_population_sum"]
            != profiles[source["id"]]["known_population_sum"]
        ):
            raise ValueError("normalisation did not conserve known population")
        if report["unknown_count_cells"] != sum(
            profiles[source["id"]]["blank_count_cells"].values()
        ):
            raise ValueError("normalisation did not conserve unknown cells")
        populations.append(report)
        print(
            source["id"], "known counts conserved; unknown cells retained", flush=True
        )
    mortality_path = verified_path(sources[config["mortality_source_id"]], args.raw_dir)
    metadata_path = verified_path(sources["mortality_national_series"], args.raw_dir)
    if not profile_mortality(mortality_path, metadata_path, region=None)[
        "covers_single_ages_0_99_2015_2024"
    ]:
        raise ValueError("mortality units or coverage unverified")
    mortality = normalise_mortality(
        mortality_path, args.output_dir / "mortality_2015_2024.csv", config
    )
    mortality["source_sha256"] = sources[config["mortality_source_id"]]["sha256"]
    result = {
        "production_ready": False,
        "stage": "normalised_audit_inputs",
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "aliases_sha256": hashlib.sha256(aliases_path.read_bytes()).hexdigest(),
        "population": populations,
        "mortality": mortality,
        "release_blockers": [
            "Unknown baseline counts remain null",
            "Endpoint differences from INE totals remain unresolved",
            "Geography crosswalk and historical parents require review",
        ],
        "legacy_cli_compatible": False,
        "reason": "Nullable populations, excluded age groups and raw-vintage geography must pass release contracts before model input export.",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
