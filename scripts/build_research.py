"""Build observed research results; never promote them through official gates."""

import csv
import gc
import gzip
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from shapely.ops import unary_union

from madrid_demography.acquisition import read_lock
from madrid_demography.boundary_audit import read_sections
from madrid_demography.config import ModelConfig
from madrid_demography.export import dumps, write_bundle
from madrid_demography.geography import overlay, wgs84
from madrid_demography.io import ContractError, Geography
from madrid_demography.model import build_analysis
from madrid_demography.parent_audit import read_membership
from madrid_demography.qa import validate_analysis
from madrid_demography.research import (
    COUNT_KEYS,
    independent_expected,
    monthly_control,
    national_schedules,
    pinned_path,
    read_research_population,
    regional_sensitivity,
)

OUT = Path("data/derived/research-site")
AUDIT = Path("docs/audit/research-results.json")
MODEL = ModelConfig.read("config/research.json")
CITY = {
    "MAD": Geography(
        "MAD",
        "Madrid · toda la ciudad",
        "city",
        None,
        "unchanged",
        "city_total_without_spatial_allocation",
    )
}


def summary(analysis):
    area = next(a for a in analysis["areas"] if a["level"] == "city")
    return {k: v for k, v in area.items() if k not in ("profile", "composition")}


def analyse(start, end, mortality, year0, year1, terminal=100, half=False, geos=None):
    result = build_analysis(
        start,
        end,
        mortality,
        geos or CITY,
        year0,
        year1,
        dataset_kind="research",
        terminal_age=terminal,
        half_age=half,
        min_expected=MODEL.min_expected,
    )
    qa = validate_analysis(result, geos or CITY)
    if not qa["passed"]:
        raise ContractError("Research arithmetic failed")
    return result


def independent_check(result, start, lives, qx):
    y0, y1 = result["start_year"], result["end_year"]
    independently = independent_expected(start, lives, y0, y1, result["terminal_age"])
    eligible = [r for r in result["cohort_detail"] if r["cohort_eligible"]]
    # Published qx has six decimals per thousand; rounding bound 0.5e-9 annually.
    # Published lx has six decimals in survivors; propagate an additional safe bound.
    differences, total_bound = [], 0.0
    for row in eligible:
        key = (row["area_id"], row["age"], row["sex"], row["nationality"])
        baseline_age = row["age"] - (y1 - y0)
        bound = row["baseline"] * sum(
            0.5e-9 + 1e-6 / lives[(y, baseline_age + y - y0, row["sex"])].__float__()
            for y in range(y0, y1)
        )
        delta = abs(row["expected"] - independently.get(key, 0.0))
        if delta > bound + 1e-7:
            raise ContractError(
                f"Independent lx survival differs beyond publication rounding: {key}, {delta}, {bound}"
            )
        differences.append(delta)
        total_bound += bound
    return {
        "passed": True,
        "cells": len(eligible),
        "formulation": "40-digit Decimal annual population propagation using published lx ratios, independently of qx survival helper",
        "maximum_cell_difference": max(differences),
        "total_expected_qx": sum(r["expected"] for r in eligible),
        "total_expected_lx": sum(independently.values()),
        "total_rounding_bound": total_bound,
        "publication_rounding_qx_per_mille": 0.000001,
        "publication_rounding_lx": 0.000001,
    }


def control_sources():
    records = []
    for year in range(2014, 2026):
        for kind in ("ages", "total"):
            receipt = json.loads(
                Path(
                    f"docs/audit/research-controls/{year}-{kind}.receipt.json"
                ).read_text()
            )
            records.append(
                {
                    "id": f"monthly_city_{year}_{kind}",
                    "url": receipt["url"],
                    "provider": "Ayuntamiento de Madrid · Banco de Datos Municipal",
                    "reference_date": f"{year}-01-01",
                    "sha256": receipt["sha256"],
                    "request": receipt["request"],
                    "role": "city_monthly_control",
                    "receipt": f"docs/audit/research-controls/{year}-{kind}.receipt.json",
                }
            )
    return records


def evidence():
    keys = [
        "source_checksums",
        "reference_dates",
        "annual_profiles",
        "published_totals",
        "mortality_coverage",
        "boundary_audit",
        "historical_parents",
        "independent_survival",
        "sensitivity_review",
        "licensing",
    ]
    return {
        key: {"passed": False, "artifact": str(AUDIT), "reviewed_by": None}
        for key in keys
    }


def export(result, geos, polygons, name, sources, sensitivities=None, coverage=None):
    config = ModelConfig(
        **{
            **MODEL.to_dict(),
            "start_date": f"{result['start_year']}-01-01",
            "end_date": f"{result['end_year']}-01-01",
            "mortality_region": "España (INE 27153)",
            "zone_version": name + "-research-v1",
            "dataset_kind": "research",
            "terminal_age": 100,
        }
    )
    target = OUT / "data" / name
    if target.exists():
        shutil.rmtree(target)
    manifest = write_bundle(
        result,
        config,
        geos,
        polygons,
        target,
        evidence=evidence(),
        sources=sources + control_sources(),
        sensitivities=sensitivities,
    )
    if coverage:
        manifest["coverage_note"] = coverage
    manifest["official_release_passed"] = False
    manifest["research_validation"] = str(AUDIT)
    # Keep CSV practical to publish, along with independently readable Parquet.
    csvpath = target / "downloads/cohort_detail.csv"
    compressed = csvpath.with_suffix(".csv.gz")
    compressed.write_bytes(gzip.compress(csvpath.read_bytes(), mtime=0))
    csvpath.unlink()
    manifest["downloads"]["csv"] = "downloads/cohort_detail.csv.gz"
    for key in ("csv", "parquet"):
        path = target / manifest["downloads"][key]
        manifest.setdefault("download_checksums", {})[key] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
    (target / "manifest.json").write_bytes(dumps(manifest))
    return {
        "id": name,
        "label": name.replace("-", "–") + " · investigación",
        "manifest": name + "/manifest.json",
        "inclusive_manifest": name + "/manifest.json",
    }


def components(graph):
    seen = set()
    for node in sorted(graph):
        if node in seen:
            continue
        pending, group = [node], set()
        while pending:
            item = pending.pop()
            if item in group:
                continue
            group.add(item)
            pending.extend(graph[item] - group)
        seen.update(group)
        yield sorted(group)


def common_parents(result, memberships, level):
    graph, zone_nodes = defaultdict(set), {}
    for component in result["components"]:
        nodes = set()
        for vintage, side in ((2015, "old"), (2025, "new")):
            for gid in component[side + "_ids"]:
                parents = memberships[vintage].get(gid)
                if not parents:
                    raise ContractError("Missing raw parent in mapped section")
                for district, barrio in parents:
                    if barrio == "0000":
                        raise ContractError("Unknown barrio in mapped section")
                    nodes.add((vintage, district if level == "district" else barrio))
        for n in nodes:
            graph[n].update(nodes - {n})
        zone_nodes[component["zone_id"]] = nodes
    groups, membership = {}, {}
    for group in components(graph):
        codes = sorted({code for vintage, code in group})
        gid = ("D-" if level == "district" else "B-") + "+".join(codes)
        groups[gid] = {
            "id": gid,
            "vintage_codes": [list(n) for n in group],
            "raw_codes": codes,
        }
        for node in group:
            membership[node] = gid
    assignment = {}
    for zid, nodes in zone_nodes.items():
        mapped = {membership[n] for n in nodes}
        if len(mapped) != 1:
            raise ContractError("Common parent partition failed")
        assignment[zid] = mapped.pop()
    return groups, assignment


def spatial(sources, qx, report):
    geometry, memberships, names = {}, {}, {"district": {}, "barrio": {}}
    for y in (2015, 2025):
        source = sources[f"padron_january_{y}"]
        path = pinned_path(source)
        memberships[y], _, _, _ = read_membership(path, source)
        with path.open(encoding=source["encoding"], newline="") as handle:
            for raw in csv.DictReader(handle, delimiter=source["delimiter"]):
                r = {k.upper(): v.strip() for k, v in raw.items()}
                names["district"][f"{int(r['COD_DISTRITO']):02d}"] = r[
                    "DESC_DISTRITO"
                ].title()
                names["barrio"][f"{int(r['COD_DIST_BARRIO']):04d}"] = r[
                    "DESC_BARRIO"
                ].title()
        geometry[y], metadata = read_sections(pinned_path(sources[f"sections_{y}"]))
        if metadata["invalid_or_empty_ids"]:
            raise ContractError("Invalid source polygon")
    result = overlay(
        geometry[2015], geometry[2025], MODEL.overlap_tolerance, MODEL.material_overlap
    )
    if any(c["quality_status"] == "unreliable" for c in result["components"]):
        raise ContractError("Cannot publish incompatible common zones as exact")
    groups, assignment = {}, {}
    for level in ("district", "barrio"):
        groups[level], assignment[level] = common_parents(result, memberships, level)
    geos = {
        "MAD-MAPPED": Geography(
            "MAD-MAPPED",
            "Madrid · secciones cartografiadas",
            "city",
            None,
            "exact_harmonisation",
            "research_common_section_unions",
        )
    }
    polygons = {
        "section": result["zones"],
        "barrio": {},
        "district": {},
        "city": {"MAD-MAPPED": unary_union(list(result["zones"].values()))},
    }
    parent_report = []
    for level in ("district", "barrio"):
        for gid, group in groups[level].items():
            zones = [z for z, parent in assignment[level].items() if parent == gid]
            polygons[level][gid] = unary_union([result["zones"][z] for z in zones])
            parents = {assignment["district"][z] for z in zones}
            if len(parents) != 1:
                raise ContractError("Common barrio crosses common district")
            parent = "MAD-MAPPED" if level == "district" else parents.pop()
            name = " + ".join(names[level][c] for c in group["raw_codes"])
            name += " · ámbito común"
            geos[gid] = Geography(
                gid,
                name,
                level,
                parent,
                "exact_harmonisation",
                "research_parent_pooling_from_both_vintage_raw_memberships",
            )
            parent_report.append(
                dict(
                    group,
                    level=level,
                    parent_id=parent,
                    zones=len(zones),
                    official_historical_parent_verified=False,
                )
            )
    for c in result["components"]:
        zid = c["zone_id"]
        geos[zid] = Geography(
            zid,
            "Zona " + zid,
            "section",
            assignment["barrio"][zid],
            c["quality_status"],
            "research_common_union_" + c["classification"],
        )
    populations, accounting = {}, {}
    for y, vintage in ((2015, "old"), (2025, "new")):
        zone_map = {
            r["source_id"]: r["zone_id"]
            for r in result["crosswalk"]
            if r["vintage"] == vintage
        }
        _, populations[y], _, accounting[y] = read_research_population(
            sources[f"padron_january_{y}"], zone_map
        )
    analysis = analyse(populations[2015], populations[2025], qx, 2015, 2025, geos=geos)
    fields = [
        "id",
        "name",
        "level",
        "parent_id",
        "boundary_status",
        "baseline",
        "expected",
        "actual",
        "residual",
        "residual_per_1000",
        "rate_suppressed",
    ]
    with Path("reports/research-area-results.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(analysis["areas"])
    report["spatial"] = {
        "summary": summary(analysis),
        "area_counts": dict(Counter(g.level for g in geos.values())),
        "annual_accounting": accounting,
        "common_parent_groups": parent_report,
        "maximum_symmetric_difference_ratio": max(
            c["symmetric_difference_ratio"] for c in result["components"]
        ),
        "all_weights_one": True,
        "official_historical_parents_verified": False,
        "policy": "Pool complete common section zones and all affected administrative codes across vintages; do not select majority parents or split population by land area",
        "interpretation": "Common research aggregates, not official dated barrio/district boundaries",
    }
    coverage = (
        "Ámbitos comunes de investigación, derivados de secciones INE y códigos de ambos años. "
        "No son límites administrativos históricos aprobados. Fuera del mapa: 12 personas en 2015 y 5 en 2025; "
        "1 edad inválida adicional en 2015. El conjunto de toda la ciudad se ofrece por separado."
    )
    return export(
        analysis,
        geos,
        {level: wgs84(p) for level, p in polygons.items()},
        "2015-2025-areas",
        list(sources.values()),
        coverage=coverage,
    )


def main():
    sources = {s["id"]: s for s in read_lock("sources.lock.yml")["sources"]}
    qx, lx_qx, lives = national_schedules(sources["mortality_national_table"])
    madrid, madrid_meta = regional_sensitivity(sources["mortality_table"], qx)
    report = {
        "dataset_kind": "research",
        "official_release_passed": False,
        "annual_controls": [],
        "independent_survival": {},
        "sensitivities": [],
        "intermediate_years": [],
        "city_windows": {},
    }
    annual = {}
    for y in range(2014, 2026):
        annual[y], _, _, accounting = read_research_population(
            sources[f"padron_january_{y}"], require_matching_controls=False
        )
        if not accounting["monthly_controls_matched"]:
            # A failed reconciliation never licenses local zero inference.
            values, _ = monthly_control(y, "ages")
            annual[y] = {
                ("MAD", age, *COUNT_KEYS[c]): count
                for (age, c), count in values.items()
            }
            full, _ = monthly_control(y, "total")
            for column, (sex, nat) in COUNT_KEYS.items():
                remainder = full[("total", column)] - sum(
                    values[(a, column)] for a in range(100)
                )
                if remainder < 0:
                    raise ContractError(
                        "Negative open-age remainder in monthly city controls"
                    )
                annual[y][("MAD", 100, sex, nat)] = remainder
            accounting["analytical_city_source"] = (
                "Explicit monthly bank city age/sex/nationality counts; raw file excluded from this year model"
            )
            accounting["analytical_city_stock"] = sum(annual[y].values())
        report["annual_controls"].append(accounting)
        print(
            "Annual reconciliation",
            y,
            accounting["known_total"],
            accounting["monthly_controls_matched"],
            flush=True,
        )
    OUT.mkdir(parents=True, exist_ok=True)
    Path("reports").mkdir(exist_ok=True)
    for name in ("index.html", "app.js", "charts.js", "styles.css"):
        shutil.copyfile(Path("web") / name, OUT / name)
    (OUT / ".nojekyll").write_text("")
    windows = []
    city_geometry, _ = read_sections(pinned_path(sources["sections_2025"]))
    city_polygon = {"city": wgs84({"MAD": unary_union(list(city_geometry.values()))})}
    for y0, y1 in ((2015, 2025), (2014, 2024)):
        result = analyse(annual[y0], annual[y1], qx, y0, y1)
        report["city_windows"][f"{y0}-{y1}"] = summary(result)
        report["independent_survival"][f"{y0}-{y1}"] = independent_check(
            result, annual[y0], lives, qx
        )
        variants = []
        for label, mortality, terminal, half in (
            ("national_endpoint_under90", qx, 90, False),
            ("national_endpoint_under95", qx, 95, False),
            ("national_endpoint_under100", qx, 100, False),
            ("national_half_age_under100", qx, 100, True),
            ("national_lx_under100", lx_qx, 100, False),
            ("Madrid_closed_band_approximation_under95", madrid, 95, False),
        ):
            s = summary(
                analyse(annual[y0], annual[y1], mortality, y0, y1, terminal, half)
            )
            variants.append(
                {
                    "area_id": "MAD",
                    "scenario": label,
                    "start_year": y0,
                    "end_year": y1,
                    "terminal_age": terminal,
                    "expected": s["expected"],
                    "actual": s["actual"],
                    "residual": s["residual"],
                    "residual_per_1000": s["residual_per_1000"],
                    "expected_difference": s["expected"] - summary(result)["expected"],
                }
            )
        report["sensitivities"].extend(variants)
        windows.append(
            export(
                result,
                CITY,
                city_polygon,
                f"{y0}-{y1}-city",
                list(sources.values()),
                variants,
                "Toda la ciudad; el mapa usa el contorno de secciones INE 2025 solo como referencia. "
                "En 2015 se excluye 1 persona con edad inválida 135.",
            )
        )
    report["Madrid_sensitivity"] = madrid_meta
    for y in range(2016, 2026):
        s = summary(
            analyse(annual[2015], annual[y], qx, 2015, y, terminal=90 + y - 2015)
        )
        report["intermediate_years"].append(
            dict(
                endpoint_year=y,
                baseline_ages="0–89 fixed across endpoints",
                endpoint_min_age=y - 2015,
                endpoint_max_age=89 + y - 2015,
                **s,
            )
        )
    windows.insert(0, spatial(sources, qx, report))
    gc.collect()
    (OUT / "data/catalog.json").write_bytes(
        dumps({"schema_version": 2, "dataset_kind": "research", "windows": windows})
    )
    report["limitations"] = [
        "Research only: conditional blank-to-zero policy under matched exhaustive monthly controls; raw nulls preserved.",
        "National mortality used for headline; Madrid closed-band sensitivity is an explicit approximation, ages 95+ never expanded.",
        "Residual is a stock difference incorporating moves, registration, nationality changes and model error; not migration flows.",
        "Exact research common-zone arithmetic does not establish historical administrative parent validity.",
        "Official release gates remain closed pending evidence and review; source publication totals are different from the monthly series.",
    ]
    AUDIT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k in ("city_windows", "independent_survival")
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
