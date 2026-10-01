#!/usr/bin/env python3
"""Build deterministic, clearly labelled interface demonstration data."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from madrid_demography.io import Geography  # noqa: E402
from madrid_demography.model import build_analysis  # noqa: E402


def main() -> None:
    districts = [
        ("D01", "Centro", 0.05),
        ("D02", "Arganzuela", 0.12),
        ("D03", "Retiro", -0.03),
        ("D04", "Salamanca", -0.07),
        ("D05", "Chamartín", 0.02),
        ("D06", "Tetuán", 0.16),
        ("D07", "Chamberí", -0.01),
        ("D08", "Fuencarral-El Pardo", 0.10),
        ("D09", "Moncloa-Aravaca", 0.04),
    ]
    geographies = {
        "MAD": Geography("MAD", "Madrid", "city", None, "unchanged", "aggregate")
    }
    start = {}
    end = {}
    mortality = {}
    for year in range(2015, 2025):
        for age in range(131):
            for sex in ("male", "female"):
                base = 0.00025 + (max(age - 45, 0) / 52) ** 4 * 0.035
                if age > 90:
                    base += (age - 90) * 0.013
                mortality[(year, age, sex)] = min(base * (1.12 if sex == "male" else 0.88), 0.48)

    for index, (area_id, name, growth) in enumerate(districts):
        status = "estimated_harmonisation" if area_id == "D08" else "unchanged"
        geographies[area_id] = Geography(area_id, name, "district", "MAD", status, "demo")
        for age in range(101):
            age_curve = 320 + 720 * math.exp(-((age - (39 + index % 4)) / 24) ** 2)
            for sex_index, sex in enumerate(("male", "female")):
                for nationality in ("ESP", "EXT"):
                    foreign_share = 0.24 if nationality == "EXT" else 0.76
                    start_count = round(age_curve * foreign_share * (0.96 + sex_index * 0.08))
                    start[(area_id, age, sex, nationality)] = start_count
                    if age < 10:
                        endpoint = (280 + index * 10) * foreign_share
                    else:
                        baseline_age = age - 10
                        baseline = (320 + 720 * math.exp(-((baseline_age - (39 + index % 4)) / 24) ** 2))
                        survival = 1.0
                        for offset, year in enumerate(range(2015, 2025)):
                            survival *= 1 - mortality[(year, baseline_age + offset, sex)]
                        age_effect = 0.28 * math.exp(-((age - 30) / 12) ** 2) - 0.08 * math.exp(-((age - 68) / 16) ** 2)
                        nationality_effect = 0.11 if nationality == "EXT" else -0.015
                        endpoint = baseline * foreign_share * (0.96 + sex_index * 0.08) * survival
                        endpoint *= 1 + growth + age_effect + nationality_effect
                    end[(area_id, age, sex, nationality)] = max(0, round(endpoint))

    result = build_analysis(start, end, mortality, geographies, 2015, 2025, dataset_kind="demonstration")
    result["notice"] = "Datos simulados para revisar la interfaz; no son estadísticas oficiales."
    output = ROOT / "web" / "data" / "analysis.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote demonstration data to {output}")


if __name__ == "__main__":
    main()

