"""Explicit research variants; no scenario replaces unadjusted results."""

from collections import defaultdict
from .io import ContractError
from .model import survival_probability


def births_counterfactual(
    start,
    mortality,
    fertility,
    start_year,
    end_year,
    *,
    male_share=0.512,
    units="per_1000",
):
    if units != "per_1000" or not 0 < male_share < 1:
        raise ContractError(
            "birth scenario requires documented ASFR/1000 and sex ratio"
        )
    women = defaultdict(float)
    for (gid, age, sex, nat), count in start.items():
        if sex == "female" and age <= 49:
            women[(gid, age)] += count
    children = defaultdict(float)
    births = defaultdict(float)
    for year in range(start_year, end_year):
        next_women = defaultdict(float)
        for (gid, age), count in women.items():
            survival = survival_probability(age, "female", year, year + 1, mortality)
            if 15 <= age <= 49:
                key = (year, age)
                if key not in fertility:
                    raise ContractError(f"missing fertility {key}")
                rate = fertility[key]
                if not 0 <= rate <= 1000:
                    raise ContractError("invalid ASFR")
                midyear = count * (1 + survival) / 2
                newborns = rate / 1000 * midyear
                births[(gid, year)] += newborns
                for sex, share in [("male", male_share), ("female", 1 - male_share)]:
                    # Uniform birth timing: half-year infant exposure followed by full years.
                    infant = (
                        survival_probability(0, sex, year, year + 1, mortality) ** 0.5
                    )
                    later = survival_probability(1, sex, year + 1, end_year, mortality)
                    children[(gid, end_year - year - 1, sex)] += (
                        newborns * share * infant * later
                    )
            if age < 49:
                next_women[(gid, age + 1)] += count * survival
        women = next_women
    return {
        "method": "baseline women only; mid-year exposure; uniform birth timing; total nationality only",
        "births": [
            dict(area_id=g, year=y, births=v) for (g, y), v in sorted(births.items())
        ],
        "children": [
            dict(area_id=g, age=a, sex=s, expected=v)
            for (g, a, s), v in sorted(children.items())
        ],
    }


def nationality_scenarios(
    start, mortality, hazards, start_year, end_year, multipliers=(0.5, 1.0, 1.5)
):
    results = []
    for multiplier in multipliers:
        foreign = defaultdict(float)
        surviving_transfers = defaultdict(float)
        for (gid, age, sex, nat), count in start.items():
            if nat == "EXT":
                foreign[(gid, age, sex)] += count
        for year in range(start_year, end_year):
            next_foreign = defaultdict(float)
            for (gid, age, sex), count in foreign.items():
                key = (year, age, sex)
                if key not in hazards:
                    raise ContractError(f"missing nationality hazard {key}")
                hazard = hazards[key]
                if not 0 <= hazard <= 1:
                    raise ContractError("nationality hazard outside [0,1]")
                transfer = count * min(hazard * multiplier, 1)
                # Acquisition at beginning of year; survival to endpoint; no newborn allocation.
                survival = survival_probability(age, sex, year, end_year, mortality)
                surviving_transfers[(gid, age + end_year - year, sex)] += (
                    transfer * survival
                )
                next_foreign[(gid, age + 1, sex)] += (
                    count - transfer
                ) * survival_probability(age, sex, year, year + 1, mortality)
            foreign = next_foreign
        results.append(
            {
                "multiplier": multiplier,
                "adjustments": [
                    dict(area_id=g, age=a, sex=s, ESP=-v, EXT=v, total=0.0)
                    for (g, a, s), v in sorted(surviving_transfers.items())
                ],
            }
        )
    return {
        "method": "regional acquisition hazard; beginning-year timing; scenario only, not observed section reclassifications",
        "scenarios": results,
    }


def compare_analyses(primary, variants):
    base = {a["id"]: a for a in primary["areas"]}
    output = []
    for label, analysis in variants.items():
        for area in analysis["areas"]:
            reference = base[area["id"]]
            output.append(
                {
                    "scenario": label,
                    "area_id": area["id"],
                    "expected": area["expected"],
                    "residual": area["residual"],
                    "expected_difference": area["expected"] - reference["expected"],
                    "relative_difference": (
                        area["expected"] / reference["expected"] - 1
                    )
                    if reference["expected"]
                    else None,
                }
            )
    return output
