from __future__ import annotations
from collections import defaultdict
import math
from .io import ContractError

QUALITY = {
    "unchanged": 0,
    "exact_harmonisation": 1,
    "estimated_harmonisation": 2,
    "unreliable": 3,
}


def survival_probability(age, sex, start_year, end_year, mortality, *, half_age=False):
    probability = 1.0
    for offset, year in enumerate(range(start_year, end_year)):
        key = (year, age + offset, sex)
        if key not in mortality:
            raise ContractError(f"missing mortality probability for year/age/sex {key}")
        qx = mortality[key]
        if half_age:
            adjacent = (year, age + offset + 1, sex)
            if adjacent not in mortality:
                raise ContractError(
                    f"missing mortality probability for half-age {adjacent}"
                )
            qx = 0.5 * (qx + mortality[adjacent])
        if not math.isfinite(qx) or not 0 <= qx <= 1:
            raise ContractError("mortality probability outside [0,1]")
        probability *= 1 - qx
    return probability


def _ancestors(area_id, geographies):
    output = []
    while area_id:
        if area_id in output:
            raise ContractError("geography hierarchy cycle")
        if area_id not in geographies:
            raise ContractError(f"unknown parent {area_id}")
        output.append(area_id)
        area_id = geographies[area_id].parent_id
    return output


def build_analysis(
    start,
    end,
    mortality,
    geographies,
    start_year,
    end_year,
    *,
    dataset_kind="demonstration",
    min_expected=20,
    terminal_age=131,
    half_age=False,
):
    if end_year <= start_year:
        raise ContractError("end year must be later than start year")
    interval = end_year - start_year
    leaf_ids = {k[0] for k in start} | {k[0] for k in end}
    if leaf_ids - geographies.keys():
        raise ContractError("population contains unknown geographies")
    ancestors = {gid: _ancestors(gid, geographies) for gid in geographies}
    if any(any(a in leaf_ids for a in ancestors[gid][1:]) for gid in leaf_ids):
        raise ContractError("population mixes leaves with their aggregates")
    for population in (start, end):
        for (gid, age, sex, nat), count in population.items():
            if (
                sex not in {"male", "female"}
                or nat not in {"ESP", "EXT"}
                or not 0 <= age <= 130
                or not math.isfinite(count)
                or count < 0
            ):
                raise ContractError("invalid analytical population cell")
    cells = defaultdict(lambda: {"baseline": 0.0, "expected": 0.0, "actual": 0.0})
    # Source populations are independent of shifted baseline, for composition comparisons.
    composition = defaultdict(float)
    for label, population in [(start_year, start), (end_year, end)]:
        for (leaf, age, sex, nat), count in population.items():
            for gid in ancestors[leaf]:
                composition[(gid, label, age, nat)] += count
    for (leaf, age, sex, nat), count in start.items():
        endpoint_age = age + interval
        survival = (
            survival_probability(
                age, sex, start_year, end_year, mortality, half_age=half_age
            )
            if endpoint_age < terminal_age and count
            else 0.0
        )
        for gid in ancestors[leaf]:
            cell = cells[(gid, endpoint_age, sex, nat)]
            cell["baseline"] += count
            cell["expected"] += count * survival
    for (leaf, age, sex, nat), count in end.items():
        for gid in ancestors[leaf]:
            cells[(gid, age, sex, nat)]["actual"] += count
    detail = []
    collapsed = defaultdict(lambda: {"baseline": 0.0, "expected": 0.0, "actual": 0.0})
    for (gid, age, sex, nat), values in sorted(cells.items()):
        eligible = interval <= age < terminal_age
        row = dict(
            area_id=gid,
            age=age,
            sex=sex,
            nationality=nat,
            **values,
            cohort_eligible=eligible,
            residual=values["actual"] - values["expected"] if eligible else None,
            exclusion_reason="born_during_interval"
            if age < interval
            else "terminal_age"
            if age >= terminal_age
            else None,
        )
        if not eligible:
            row["expected"] = None
        detail.append(row)
        for field in values:
            collapsed[(gid, age, nat)][field] += values[field]
    profiles = defaultdict(list)
    for (gid, age, nat), values in sorted(collapsed.items()):
        eligible = interval <= age < terminal_age
        profiles[gid].append(
            dict(
                age=age,
                nationality=nat,
                baseline=values["baseline"],
                actual=values["actual"],
                cohort_eligible=eligible,
                expected=values["expected"] if eligible else None,
                residual=values["actual"] - values["expected"] if eligible else None,
                rate_suppressed=not eligible or values["expected"] < min_expected,
                exclusion_reason="born_during_interval"
                if age < interval
                else "terminal_age"
                if age >= terminal_age
                else None,
            )
        )
    effective = {gid: geo.boundary_status for gid, geo in geographies.items()}
    affected = defaultdict(float)
    totals = defaultdict(float)
    leaf_totals = defaultdict(float)
    for key, count in start.items():
        leaf_totals[key[0]] += count
    for leaf in leaf_ids:
        count = leaf_totals[leaf]
        for gid in ancestors[leaf]:
            totals[gid] += count
            if QUALITY[geographies[leaf].boundary_status] >= 2:
                affected[gid] += count
            if QUALITY[effective[gid]] < QUALITY[geographies[leaf].boundary_status]:
                effective[gid] = geographies[leaf].boundary_status
    composition_by_area = defaultdict(list)
    for (gid, year, age, nat), count in sorted(composition.items()):
        composition_by_area[gid].append(
            dict(year=year, age=age, nationality=nat, population=count)
        )
    areas = []
    for gid, geo in geographies.items():
        rows = profiles[gid]
        eligible = [r for r in rows if r["cohort_eligible"]]
        expected = sum(r["expected"] for r in eligible)
        actual = sum(r["actual"] for r in eligible)
        baseline = sum(r["baseline"] for r in eligible)
        residual = actual - expected
        sparse = expected < min_expected
        areas.append(
            dict(
                id=gid,
                name=geo.name,
                level=geo.level,
                parent_id=geo.parent_id,
                boundary_status=effective[gid],
                boundary_method=geo.boundary_method,
                affected_share=affected[gid] / totals[gid] if totals[gid] else 0,
                reliability_note="Incluye asignación estimada o zonas no fiables"
                if QUALITY[effective[gid]] >= 2
                else "Agregación exacta; revisar auditoría de límites",
                baseline=baseline,
                expected=expected,
                actual=actual,
                residual=residual,
                observed_change=actual - baseline,
                modelled_deaths=baseline - expected,
                residual_per_1000=1000 * residual / expected
                if expected and not sparse
                else None,
                annualised_residual_per_1000=1000 * residual / expected / interval
                if expected and not sparse
                else None,
                rate_suppressed=sparse,
                default_visible=QUALITY[effective[gid]] < 2,
                observed_under_interval=sum(
                    r["actual"] for r in rows if r["age"] < interval
                ),
                observed_terminal=sum(
                    r["actual"] for r in rows if r["age"] >= terminal_age
                ),
                profile=rows,
                composition=composition_by_area[gid],
            )
        )
    return dict(
        schema_version=2,
        dataset_kind=dataset_kind,
        start_year=start_year,
        end_year=end_year,
        interval_years=interval,
        terminal_age=terminal_age,
        min_expected=min_expected,
        method="annual sex-specific cohort survival; same schedule for ESP and EXT",
        areas=sorted(areas, key=lambda a: (a["level"], a["name"])),
        cohort_detail=detail,
    )
