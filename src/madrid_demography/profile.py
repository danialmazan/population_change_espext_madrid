"""Profile raw January padrón files without interpreting blanks as zero."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from .acquire import load_manifest


COUNTS = (
    "ESPANOLESHOMBRES",
    "ESPANOLESMUJERES",
    "EXTRANJEROSHOMBRES",
    "EXTRANJEROSMUJERES",
)


def profile_population(path: Path, encoding: str, delimiter: str) -> dict:
    result = {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "encoding": encoding,
        "delimiter": delimiter,
        "rows": 0,
        "duplicate_section_age_rows": 0,
        "invalid_ages": 0,
        "invalid_counts": 0,
        "invalid_geography_rows": 0,
        "malformed_rows": 0,
        "special_geography_rows": 0,
        "special_geography_known_population": 0,
    }
    ages, keys, sections, barrios, districts = Counter(), set(), set(), set(), set()
    blank, totals, dates, parent_conflicts = Counter(), Counter(), {}, set()
    open_ages, section_population = Counter(), Counter()
    parents = {}
    with path.open(encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        result["raw_header"] = reader.fieldnames
        aliases = {name: name.strip().upper() for name in reader.fieldnames or []}
        required = set(COUNTS) | {
            "COD_DISTRITO",
            "COD_DIST_BARRIO",
            "COD_DIST_SECCION",
            "COD_EDAD_INT",
        }
        if required - set(aliases.values()):
            raise ValueError(
                f"missing fields: {sorted(required - set(aliases.values()))}"
            )
        for raw in reader:
            result["rows"] += 1
            if None in raw or any(value is None for value in raw.values()):
                result["malformed_rows"] += 1
                continue
            row = {aliases[key]: value.strip() for key, value in raw.items()}
            try:
                district = int(row["COD_DISTRITO"])
                section = int(row["COD_DIST_SECCION"])
                barrio = int(row["COD_DIST_BARRIO"])
                if not 1 <= district <= 21 or section // 1000 != district:
                    raise ValueError("inconsistent district/section")
            except ValueError:
                result["invalid_geography_rows"] += 1
                section = None
            if section is not None:
                districts.add(district)
                sections.add(section)
                barrios.add(barrio)
                previous = parents.setdefault(section, barrio)
                if previous != barrio:
                    parent_conflicts.add(section)
            try:
                age = int(row["COD_EDAD_INT"])
                ages[age] += 1
                if not 0 <= age <= 130:
                    result["invalid_ages"] += 1
            except ValueError:
                age = row["COD_EDAD_INT"]
                if age == "100 o +":
                    open_ages[age] += 1
                else:
                    result["invalid_ages"] += 1
            key = (
                (section, age)
                if section is not None
                else (
                    row["COD_DISTRITO"],
                    row["COD_DIST_BARRIO"],
                    "missing_section",
                    age,
                )
            )
            if key in keys:
                result["duplicate_section_age_rows"] += 1
            keys.add(key)
            special = section is not None and (
                barrio == 0 or section % 1000 in (0, 888, 999)
            )
            if special:
                result["special_geography_rows"] += 1
            for column in COUNTS:
                value = row[column]
                if value == "":
                    blank[column] += 1
                    continue
                try:
                    number = int(value)
                    if number < 0:
                        raise ValueError("negative count")
                except ValueError:
                    result["invalid_counts"] += 1
                    continue
                totals[column] += number
                if section is not None:
                    section_population[section] += number
                else:
                    result["invalid_geography_known_population"] = (
                        result.get("invalid_geography_known_population", 0) + number
                    )
                if special:
                    result["special_geography_known_population"] += number
            for column in ("FX_DATOS_INI", "FX_DATOS_FIN", "FX_CARGA"):
                if column in row:
                    dates.setdefault(column, set()).add(row[column])
    result.update(
        ages=dict(sorted(ages.items())),
        sections=len(sections),
        barrios=len(barrios),
        districts=len(districts),
        section_codes=sorted(sections),
        sections_with_multiple_barrios=sorted(parent_conflicts),
        blank_count_cells=dict(blank),
        known_population_by_column=dict(totals),
        known_population_sum=sum(totals.values()),
        open_age_labels=dict(open_ages),
        known_population_by_section=dict(sorted(section_population.items())),
        date_values={k: sorted(v) for k, v in dates.items()},
        status="requires_review"
        if blank
        or open_ages
        or result["special_geography_rows"]
        or any(
            result[k]
            for k in (
                "invalid_ages",
                "invalid_counts",
                "invalid_geography_rows",
                "malformed_rows",
                "duplicate_section_age_rows",
            )
        )
        or parent_conflicts
        else "profiled",
    )
    return result


def latest_receipt(root: Path, source: dict) -> dict | None:
    # Resolve from the caller's root, never from a receipt's machine-specific path.
    folder = root / source["id"]
    receipts = [json.loads(p.read_text()) for p in folder.glob("receipt-*.json")]
    matching = [r for r in receipts if r.get("requested_url") == source["url"]]
    receipt = max(matching, key=lambda r: r["retrieved_at"]) if matching else None
    sha = source.get("sha256")
    canonical = folder / str(sha)
    extended = folder / f"{sha}.{source['kind']}"
    path = canonical if canonical.exists() else extended
    if sha and path.exists():
        return {**(receipt or {}), "path": str(path), "sha256": sha, "status": "pinned"}
    return receipt


def profile_mortality(path: Path, series_path: Path, *, region: str | None) -> dict:
    """Check source coverage and units; do not manufacture single-age probabilities."""
    metadata = json.loads(series_path.read_bytes())
    units = sorted(
        {
            s["T3_Unidad"]
            for s in metadata
            if ". Riesgo de muerte." in s["Nombre"]
            and (region is None or s["Nombre"].startswith(region))
        }
    )
    cells, missing, ages, years = {}, 0, set(), set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter=";"):
            if region is not None and not row[
                "Comunidades y Ciudades Autónomas"
            ].endswith(region):
                continue
            if row["Funciones"] != "Riesgo de muerte" or row["Sexo"] not in (
                "Hombres",
                "Mujeres",
            ):
                continue
            age, year = row["Edad"], int(row["Periodo"])
            ages.add(age)
            years.add(year)
            if 2015 <= year <= 2024:
                value = row["Total"].strip()
                if value in ("", "..", "."):
                    missing += 1
                else:
                    key = (year, row["Sexo"], age)
                    if key in cells:
                        raise ValueError(f"duplicate mortality cell {key}")
                    cells[key] = float(value.replace(".", "").replace(",", "."))
    expected = {
        (y, s, "1 año" if a == 1 else f"{a} años")
        for y in range(2015, 2025)
        for s in ("Hombres", "Mujeres")
        for a in range(100)
    }
    missing_single = sorted(expected - set(cells))
    return {
        "region": region or "Spain",
        "risk_of_death_units": units,
        "ages": sorted(ages),
        "years": sorted(years),
        "missing_values_2015_2024": missing,
        "single_age_cells_required_0_99": len(expected),
        "single_age_cells_missing_0_99": len(missing_single),
        "missing_cell_sample": missing_single[:12],
        "risk_values_in_0_1000": all(0 <= v <= 1000 for v in cells.values()),
        "covers_single_ages_0_99_2015_2024": not missing_single
        and not missing
        and units == ["Tanto por mil"],
        "terminal_age_policy_required": True,
        "unit_conversion_if_adopted": "qx = Riesgo de muerte / 1000; never substitute Tasa de mortalidad",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("sources.lock.yml"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--report", type=Path, default=Path("docs/audit/padron_profiles.json")
    )
    args = parser.parse_args()
    profiles = []
    for source in load_manifest(args.manifest)["sources"]:
        if not (
            source["id"].startswith("padron_january_")
            and source["id"].removeprefix("padron_january_").isdigit()
        ):
            continue
        receipt = latest_receipt(args.raw_dir, source)
        entry = {"source_id": source["id"], "reference_date": source["reference_date"]}
        try:
            if not receipt or receipt["status"] == "failed":
                raise ValueError("no successful matching acquisition")
            path = Path(receipt["path"])
            if (
                source.get("sha256")
                and hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]
            ):
                raise ValueError("checksum does not match manifest")
            entry.update(
                profile_population(path, source["encoding"], source["delimiter"])
            )
        except Exception as exc:
            entry.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        profiles.append(entry)
        print(
            source["id"], entry["status"], entry.get("known_population_sum"), flush=True
        )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps({"production_ready": False, "profiles": profiles}, indent=2) + "\n"
    )
    return int(any(p["status"] == "failed" for p in profiles))


if __name__ == "__main__":
    raise SystemExit(main())
