#!/usr/bin/env python3
"""Deterministic fixtures exercising all spatial levels and two independent windows."""

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from shapely.geometry import box
from shapely.ops import unary_union
from madrid_demography.config import ModelConfig
from madrid_demography.io import Geography
from madrid_demography.model import build_analysis
from madrid_demography.scenarios import compare_analyses
from madrid_demography.export import write_bundle


def demo_window(start_year, end_year, output):
    geographies = {
        "MAD": Geography(
            "MAD", "Madrid · demostración", "city", None, "unchanged", "aggregate"
        )
    }
    start = {}
    end = {}
    mortality = {}
    shapes = {"section": {}, "barrio": {}, "district": {}, "city": {}}
    # Rectangles are explicit synthetic geometry, never official Madrid boundaries.
    names = [
        "Centro",
        "Arganzuela",
        "Retiro",
        "Salamanca",
        "Chamartín",
        "Tetuán",
        "Chamberí",
        "Fuencarral-El Pardo",
        "Moncloa-Aravaca",
    ]
    for year in range(start_year, end_year):
        for age in range(131):
            for sex in ["male", "female"]:
                mortality[(year, age, sex)] = min(
                    (
                        0.00025
                        + (max(age - 45, 0) / 52) ** 4 * 0.035
                        + max(age - 90, 0) * 0.013
                    )
                    * (1.12 if sex == "male" else 0.88),
                    0.48,
                )
    for index, name in enumerate(names):
        district = f"D{index + 1:02d}"
        barrio = f"B{index + 1:02d}"
        x = -3.76 + (index % 3) * 0.035
        y = 40.36 + (index // 3) * 0.027
        geographies[district] = Geography(
            district, name + " · demo", "district", "MAD", "unchanged", "aggregate"
        )
        geographies[barrio] = Geography(
            barrio,
            "Barrio sintético " + str(index + 1),
            "barrio",
            district,
            "unchanged",
            "aggregate",
        )
        for part in range(2):
            gid = f"28079{index + 1:02d}{part + 1:03d}"
            status = (
                "estimated_harmonisation"
                if index == 7 and part == 1
                else "unreliable"
                if index == 8 and part == 1
                else "exact_harmonisation"
                if index == 5
                else "unchanged"
            )
            geographies[gid] = Geography(
                gid,
                "Zona sintética " + gid[-5:],
                "section",
                barrio,
                status,
                "residential_capacity"
                if status == "estimated_harmonisation"
                else "excluded"
                if status == "unreliable"
                else "exact_aggregate"
                if status == "exact_harmonisation"
                else "unchanged",
            )
            shapes["section"][gid] = box(
                x + part * 0.0175, y, x + (part + 1) * 0.0175 - 0.001, y + 0.025
            )
            for age in range(100):
                for sex_i, sex in enumerate(["male", "female"]):
                    for nat in ["ESP", "EXT"]:
                        share = 0.22 if nat == "EXT" else 0.78
                        count = round(
                            (80 + 200 * math.exp(-(((age - 39 - index % 4) / 24) ** 2)))
                            * share
                            * (0.96 + sex_i * 0.08)
                        )
                        start[(gid, age, sex, nat)] = count
                        if age < 10:
                            observed = (60 + index * 2) * share
                        else:
                            base_age = age - 10
                            baseline = (
                                (
                                    80
                                    + 200
                                    * math.exp(
                                        -(((base_age - 39 - index % 4) / 24) ** 2)
                                    )
                                )
                                * share
                                * (0.96 + sex_i * 0.08)
                            )
                            survival = math.prod(
                                1 - mortality[(year, base_age + year - start_year, sex)]
                                for year in range(start_year, end_year)
                            )
                            growth = (
                                0.03 + (index - 3) * 0.012 + (start_year - 2015) * 0.008
                            )
                            effect = 0.25 * math.exp(
                                -(((age - 30) / 12) ** 2)
                            ) - 0.08 * math.exp(-(((age - 68) / 16) ** 2))
                            observed = (
                                baseline
                                * survival
                                * (
                                    1
                                    + growth
                                    + effect
                                    + (0.1 if nat == "EXT" else -0.01)
                                )
                            )
                        end[(gid, age, sex, nat)] = max(0, round(observed))
        shapes["barrio"][barrio] = unary_union(
            [
                g
                for gid, g in shapes["section"].items()
                if geographies[gid].parent_id == barrio
            ]
        )
        shapes["district"][district] = shapes["barrio"][barrio]
    shapes["city"]["MAD"] = unary_union(list(shapes["district"].values()))
    config = ModelConfig(
        start_date=f"{start_year}-01-01",
        end_date=f"{end_year}-01-01",
        zone_version=f"demo-{start_year}-{end_year}",
        dataset_kind="demonstration",
    )
    kwargs = dict(
        dataset_kind="demonstration",
        terminal_age=config.terminal_age,
        min_expected=config.min_expected,
    )
    result = build_analysis(
        start, end, mortality, geographies, start_year, end_year, **kwargs
    )
    half = build_analysis(
        start,
        end,
        mortality,
        geographies,
        start_year,
        end_year,
        half_age=True,
        **kwargs,
    )
    spain = {k: min(v * 1.05, 1.0) for k, v in mortality.items()}
    variant = build_analysis(
        start, end, spain, geographies, start_year, end_year, **kwargs
    )
    sensitivities = compare_analyses(
        result, {"half-age": half, "alternate-schedule-demo": variant}
    )
    manifest = write_bundle(
        result,
        config,
        geographies,
        shapes,
        output,
        sensitivities=sensitivities,
        sources=[
            {
                "id": "synthetic-fixtures",
                "license": "CC0-1.0",
                "note": "Deterministic artificial counts and polygons; mortality schedules are artificial",
            }
        ],
    )
    # Publish exact-only analyses alongside inclusive research analyses, never drop provenance.
    reliable = {
        gid
        for gid, geo in geographies.items()
        if geo.boundary_status in {"unchanged", "exact_harmonisation"}
    }
    exact_start = {k: v for k, v in start.items() if k[0] in reliable}
    exact_end = {k: v for k, v in end.items() if k[0] in reliable}
    exact_result = build_analysis(
        exact_start, exact_end, mortality, geographies, start_year, end_year, **kwargs
    )
    exact_shapes = {
        level: {gid: g for gid, g in polygons.items() if gid in reliable}
        for level, polygons in shapes.items()
    }
    exact_geographies = {
        gid: geo for gid, geo in geographies.items() if gid in reliable
    }
    exact_result["areas"] = [a for a in exact_result["areas"] if a["id"] in reliable]
    exact_result["cohort_detail"] = [
        r for r in exact_result["cohort_detail"] if r["area_id"] in reliable
    ]
    exact_result["coverage_note"] = (
        "Solo zonas exactas; los agregados cubren un subconjunto del territorio."
    )
    # Empty parents are retained to preserve all four levels; disclosed as subset coverage.
    exact_half = build_analysis(
        exact_start,
        exact_end,
        mortality,
        geographies,
        start_year,
        end_year,
        half_age=True,
        **kwargs,
    )
    exact_half["areas"] = [a for a in exact_half["areas"] if a["id"] in reliable]
    exact_sensitivities = compare_analyses(exact_result, {"half-age": exact_half})
    exact_manifest = write_bundle(
        exact_result,
        config,
        exact_geographies,
        exact_shapes,
        output / "exact",
        sensitivities=exact_sensitivities,
        sources=[
            {
                "id": "synthetic-exact-subset",
                "license": "CC0-1.0",
                "note": "City and parent aggregates exclude estimated/unreliable leaves",
            }
        ],
    )
    exact_manifest["coverage_note"] = exact_result["coverage_note"]
    (output / "exact" / "manifest.json").write_text(
        json.dumps(exact_manifest, ensure_ascii=False)
    )
    return manifest


def main():
    output = ROOT / "web" / "data"
    windows = []
    for start, end in [(2015, 2025), (2014, 2024)]:
        demo_window(start, end, output / f"{start}-{end}")
        windows.append(
            {
                "id": f"{start}-{end}",
                "label": f"{start}–{end} · demostración",
                "manifest": f"{start}-{end}/exact/manifest.json",
                "inclusive_manifest": f"{start}-{end}/manifest.json",
            }
        )
    (output / "catalog.json").write_text(
        json.dumps(
            {"schema_version": 2, "dataset_kind": "demonstration", "windows": windows},
            ensure_ascii=False,
        )
    )
    print("Built two demonstration windows with exact and inclusive tiers")


if __name__ == "__main__":
    main()
