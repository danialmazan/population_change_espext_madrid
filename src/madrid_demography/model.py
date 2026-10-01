from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from .io import Geography, MortalityKey, PopulationKey


def survival_probability(
    age: int,
    sex: str,
    start_year: int,
    end_year: int,
    mortality: dict[MortalityKey, float],
) -> float:
    probability = 1.0
    for offset, year in enumerate(range(start_year, end_year)):
        key = (year, age + offset, sex)
        if key not in mortality:
            raise ValueError(f"missing mortality probability for year/age/sex {key}")
        probability *= 1.0 - mortality[key]
    return probability


def _ancestors(area_id: str, geographies: dict[str, Geography]) -> list[str]:
    output = []
    current: str | None = area_id
    while current:
        output.append(current)
        current = geographies[current].parent_id
    return output


def build_analysis(
    start: dict[PopulationKey, int],
    end: dict[PopulationKey, int],
    mortality: dict[MortalityKey, float],
    geographies: dict[str, Geography],
    start_year: int,
    end_year: int,
    *,
    dataset_kind: str = "official",
) -> dict[str, Any]:
    if end_year <= start_year:
        raise ValueError("end year must be later than start year")
    interval = end_year - start_year
    leaf_ids = {key[0] for key in start} | {key[0] for key in end}
    unknown = leaf_ids - geographies.keys()
    if unknown:
        raise ValueError(f"population contains unknown geographies: {sorted(unknown)}")

    # One additive cell per area/endpoint-age/sex/nationality.
    cells: dict[tuple[str, int, str, str], dict[str, float | None]] = defaultdict(
        lambda: {"baseline": 0.0, "expected": 0.0, "actual": 0.0}
    )
    for (leaf, age, sex, nationality), count in start.items():
        endpoint_age = age + interval
        if endpoint_age > 130:
            continue
        survival = survival_probability(age, sex, start_year, end_year, mortality)
        for area_id in _ancestors(leaf, geographies):
            cell = cells[(area_id, endpoint_age, sex, nationality)]
            cell["baseline"] = float(cell["baseline"] or 0) + count
            cell["expected"] = float(cell["expected"] or 0) + count * survival

    for (leaf, age, sex, nationality), count in end.items():
        for area_id in _ancestors(leaf, geographies):
            cell = cells[(area_id, age, sex, nationality)]
            cell["actual"] = float(cell["actual"] or 0) + count

    # Collapse sex for public profiles. Endpoint ages below interval are observed-only.
    profiles: dict[tuple[str, int, str], dict[str, float]] = defaultdict(
        lambda: {"baseline": 0.0, "expected": 0.0, "actual": 0.0}
    )
    for (area_id, age, _sex, nationality), values in cells.items():
        target = profiles[(area_id, age, nationality)]
        for field in target:
            target[field] += float(values[field] or 0)

    areas: list[dict[str, Any]] = []
    by_area: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (area_id, age, nationality), values in sorted(profiles.items()):
        cohort_eligible = age >= interval
        expected = values["expected"] if cohort_eligible else None
        residual = values["actual"] - expected if expected is not None else None
        by_area[area_id].append({
            "age": age,
            "nationality": nationality,
            "baseline": round(values["baseline"], 3) if cohort_eligible else None,
            "expected": round(expected, 3) if expected is not None else None,
            "actual": round(values["actual"], 3),
            "residual": round(residual, 3) if residual is not None else None,
            "cohort_eligible": cohort_eligible,
        })

    for area_id, geo in geographies.items():
        rows = by_area.get(area_id, [])
        expected_total = sum(r["expected"] or 0 for r in rows)
        actual_total = sum(r["actual"] for r in rows if r["cohort_eligible"])
        residual_total = actual_total - expected_total
        under_ten = sum(r["actual"] for r in rows if not r["cohort_eligible"])
        areas.append({
            "id": area_id,
            "name": geo.name,
            "level": geo.level,
            "parent_id": geo.parent_id,
            "boundary_status": geo.boundary_status,
            "boundary_method": geo.boundary_method,
            "expected": round(expected_total, 3),
            "actual": round(actual_total, 3),
            "residual": round(residual_total, 3),
            "residual_per_1000": round(1000 * residual_total / expected_total, 2)
            if expected_total else None,
            "observed_under_interval": round(under_ten, 3),
            "profile": rows,
        })

    # Core identity: totals must remain additive through nationality.
    for area in areas:
        profile = area["profile"]
        calculated = sum(r["residual"] or 0 for r in profile)
        if abs(calculated - area["residual"]) > 0.01:
            raise AssertionError(f"residual identity failed for {area['id']}")

    return {
        "schema_version": 1,
        "dataset_kind": dataset_kind,
        "generated_at": date.today().isoformat(),
        "start_year": start_year,
        "end_year": end_year,
        "interval_years": interval,
        "method": "annual sex-specific cohort survival; same schedule for ESP and EXT",
        "areas": sorted(areas, key=lambda item: (item["level"], item["name"])),
    }

