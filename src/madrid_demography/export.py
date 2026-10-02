"""Parquet analytical outputs and deterministic, hashed static web artifacts."""

import csv
import gzip
import hashlib
import html
import io
import json
import subprocess
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from shapely.geometry import mapping

from .io import ContractError
from .qa import official_release_gate, validate_analysis


def dumps(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode()


def compact_research_manifest(output, manifest):
    """Keep the complete hash inventory downloadable without loading it on arrival."""
    if manifest["dataset_kind"] != "research" or "audit_inventory" in manifest:
        return manifest
    value = {
        "artifacts": manifest["artifacts"],
        "profiles": manifest["profiles"],
        "budgets": manifest["performance"]["budgets"],
    }
    body = dumps(value)
    sha = hashlib.sha256(body).hexdigest()
    name = f"inventory.{sha[:16]}.json"
    output = Path(output)
    output.joinpath(name).write_bytes(body)
    compressed = gzip.compress(body, mtime=0)
    output.joinpath(name + ".gz").write_bytes(compressed)
    ref = {
        "url": name,
        "sha256": sha,
        "bytes": len(body),
        "gzip_bytes": len(compressed),
        "kind": "audit_inventory",
    }
    manifest["audit_inventory"] = ref
    manifest["artifacts"] = {
        name: ref,
        **{k: v for k, v in value["artifacts"].items() if v["kind"] != "profile"},
    }
    manifest.pop("profiles")
    profile_budgets = [b for b in value["budgets"] if b["name"].startswith("profile-")]
    manifest["performance"]["budgets"] = [
        b for b in value["budgets"] if not b["name"].startswith("profile-")
    ]
    manifest["performance"]["budgets"].append(
        {
            "name": "all-profiles",
            "gzip_bytes": max(b["gzip_bytes"] for b in profile_budgets),
            "budget": 100000,
            "passed": all(b["passed"] for b in profile_budgets),
        }
    )
    return manifest


def topology(polygons, quantization=100000):
    if not polygons:
        return {
            "type": "Topology",
            "arcs": [],
            "objects": {"areas": {"type": "GeometryCollection", "geometries": []}},
        }
    bounds = [g.bounds for g in polygons.values()]
    xmin = min(b[0] for b in bounds)
    ymin = min(b[1] for b in bounds)
    xmax = max(b[2] for b in bounds)
    ymax = max(b[3] for b in bounds)
    scale = [
        (xmax - xmin) / (quantization - 1) or 1.0,
        (ymax - ymin) / (quantization - 1) or 1.0,
    ]
    arcs = []
    geometries = []

    def ring(coords):
        points = [
            (round((x - xmin) / scale[0]), round((y - ymin) / scale[1]))
            for x, y, *_ in coords
        ]
        previous = (0, 0)
        delta = []
        for point in points:
            delta.append([point[0] - previous[0], point[1] - previous[1]])
            previous = point
        arcs.append(delta)
        return [len(arcs) - 1]

    for gid, geom in sorted(polygons.items()):
        data = mapping(geom)
        if data["type"] == "Polygon":
            encoded = [ring(r) for r in data["coordinates"]]
        elif data["type"] == "MultiPolygon":
            encoded = [[ring(r) for r in p] for p in data["coordinates"]]
        else:
            raise ContractError("web geometry must be polygonal")
        geometries.append(
            {
                "type": data["type"],
                "id": gid,
                "properties": {"area_id": gid},
                "arcs": encoded,
            }
        )
    return {
        "type": "Topology",
        "transform": {"scale": scale, "translate": [xmin, ymin]},
        "arcs": arcs,
        "objects": {"areas": {"type": "GeometryCollection", "geometries": geometries}},
    }


def band_summary(profile, low, high, min_expected):
    rows = [r for r in profile if low <= r["age"] <= high]
    eligible = [r for r in rows if r["cohort_eligible"]]
    observed = sum(r["actual"] for r in rows)
    expected = sum(r["expected"] for r in eligible)
    partial = bool(rows) and any(not r["cohort_eligible"] for r in rows)
    # An age selection containing excluded cohorts does not get an all-age residual.
    valid = bool(eligible) and not partial
    actual = sum(r["actual"] for r in eligible)
    residual = actual - expected if valid else None
    return {
        "actual": observed,
        "expected": expected if valid else None,
        "residual": residual,
        "baseline": sum(r["baseline"] for r in eligible) if valid else None,
        "residual_per_1000": 1000 * residual / expected
        if valid and expected >= min_expected and expected
        else None,
        "denominator": expected,
        "rate_suppressed": not valid or expected < min_expected,
        "cohort_eligible": valid,
    }


def write_bundle(
    analysis,
    config,
    geographies,
    geometries_by_level,
    output,
    *,
    evidence=None,
    sources=None,
    sensitivities=None,
):
    qa = validate_analysis(analysis, geographies)
    if not qa["passed"]:
        raise ContractError("QA invariants failed")
    gate = official_release_gate(config, evidence or {}, qa)
    if config.dataset_kind != analysis["dataset_kind"]:
        raise ContractError(
            f"{config.dataset_kind} release blocked: analytical dataset kind differs from configuration"
        )
    if config.dataset_kind == "official" and not gate["passed"]:
        raise ContractError(
            "official release blocked: "
            + ", ".join(c["name"] for c in gate["checks"] if not c["passed"])
        )
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    budgets = []
    artifacts = {}

    def artifact(name, value, limit=None, kind="data"):
        body = dumps(value)
        sha = hashlib.sha256(body).hexdigest()
        filename = f"{name}.{sha[:16]}.json"
        path = output / filename
        path.write_bytes(body)
        compressed = gzip.compress(body, mtime=0)
        (output / (filename + ".gz")).write_bytes(compressed)
        if limit and len(compressed) > limit:
            raise ContractError(f"{name} exceeds compressed payload budget")
        record = {
            "url": filename,
            "sha256": sha,
            "bytes": len(body),
            "gzip_bytes": len(compressed),
            "kind": kind,
        }
        artifacts[filename] = record
        budgets.append(
            {
                "name": name,
                "gzip_bytes": len(compressed),
                "budget": limit,
                "passed": limit is None or len(compressed) <= limit,
            }
        )
        return record

    presets = config.presets()
    profile_refs = {}
    index = []
    indicator_rows = []
    agebands = []
    compositions = []
    for area in analysis["areas"]:
        profile_refs[area["id"]] = artifact(
            "profile-" + hashlib.sha256(area["id"].encode()).hexdigest()[:12],
            {
                "area": area,
                "sensitivities": [
                    s for s in (sensitivities or []) if s["area_id"] == area["id"]
                ],
            },
            100000,
            "profile",
        )
        record = {k: v for k, v in area.items() if k not in {"profile", "composition"}}
        record["profile_url"] = profile_refs[area["id"]]["url"]
        record["geometry_key"] = area["id"]
        geom = geometries_by_level.get(area["level"], {}).get(area["id"])
        record["centroid"] = next(iter(geom.centroid.coords)) if geom else None
        index.append(record)
        for preset in presets:
            stats = band_summary(
                area["profile"],
                preset["min"],
                min(preset["max"], config.terminal_age - 1)
                if preset["id"] == "cohorts"
                else preset["max"],
                config.min_expected,
            )
            indicator_rows.append(
                dict(
                    area_id=area["id"],
                    preset=preset["id"],
                    **stats,
                    boundary_status=area["boundary_status"],
                    affected_share=area["affected_share"],
                )
            )
        for age in range(0, config.terminal_age, 5):
            for nat in ["ESP", "EXT"]:
                stats = band_summary(
                    [r for r in area["profile"] if r["nationality"] == nat],
                    age,
                    min(age + 4, config.terminal_age - 1),
                    config.min_expected,
                )
                agebands.append(
                    dict(
                        area_id=area["id"],
                        age_min=age,
                        age_max=min(age + 4, config.terminal_age - 1),
                        nationality=nat,
                        **stats,
                    )
                )
        compositions.extend(
            dict(area_id=area["id"], **row) for row in area["composition"]
        )
    # Precompute denominator-aware rankings for each preset and spatial level.
    by_key = {}
    index_by_id = {a["id"]: a for a in index}
    for row in indicator_rows:
        area = index_by_id[row["area_id"]]
        by_key.setdefault((area["level"], row["preset"]), []).append(row)
    for row in indicator_rows:
        row["rank"] = None
    for rows in by_key.values():
        ranking = sorted(
            [
                r
                for r in rows
                if r["residual_per_1000"] is not None
                and r["boundary_status"] in {"unchanged", "exact_harmonisation"}
            ],
            key=lambda r: r["residual_per_1000"],
            reverse=True,
        )
        for i, row in enumerate(ranking):
            row["rank"] = i + 1
    geometries = {}
    for level, polygons in geometries_by_level.items():
        analytical = {a["id"] for a in index if a["level"] == level}
        if analytical != set(polygons):
            raise ContractError(
                f"{level}: web geometry IDs differ from analytical areas"
            )
        # Geometry remains unsimplified analytically; display simplification preserves topology.
        simplified = {
            gid: geom.simplify(0.00001, preserve_topology=True)
            for gid, geom in polygons.items()
        }
        geometries[level] = artifact(
            "geometry-" + level, topology(simplified), 1000000, "geometry"
        )
    analytical = output / "downloads"
    analytical.mkdir(exist_ok=True)
    for name, rows in [
        ("cohort_detail", analysis["cohort_detail"]),
        ("area_index", index),
        ("age_band_summary", agebands),
        ("map_indicator", indicator_rows),
        ("composition", compositions),
    ]:
        if rows:
            table = pa.Table.from_pylist(rows)
            pq.write_table(
                table,
                analytical / (name + ".parquet"),
                compression="zstd",
                use_dictionary=True,
            )
    csv_body = io.StringIO()
    writer = csv.DictWriter(
        csv_body,
        fieldnames=[
            "area_id",
            "age",
            "sex",
            "nationality",
            "baseline",
            "expected",
            "actual",
            "residual",
            "cohort_eligible",
            "exclusion_reason",
            "boundary_status",
            "boundary_method",
        ],
    )
    writer.writeheader()
    lookup = {a["id"]: a for a in index}
    for row in analysis["cohort_detail"]:
        area = lookup[row["area_id"]]
        writer.writerow(
            dict(
                row,
                boundary_status=area["boundary_status"],
                boundary_method=area["boundary_method"],
            )
        )
    (analytical / "cohort_detail.csv").write_text(csv_body.getvalue(), encoding="utf-8")
    qa["release_gate"] = gate
    qa_ref = artifact("qa", qa)
    source_ref = artifact("sources", sources or [])
    metadata_ref = artifact(
        "method",
        {
            "config": config.to_dict(),
            "formulas": {
                "expected": "P[a,s,n,t0] × ∏(1 − q[a+j,s,t0+j])",
                "residual": "Actual − Expected",
                "rate": "1000 × residual / expected",
            },
            "exclusions": {
                "born": f"0–{config.interval - 1}",
                "terminal": f"{config.terminal_age}+",
            },
            "mortality_assumptions": f"{config.mortality_region} period life tables; same sex-specific schedule for ESP and EXT",
            "nationality_caveat": "Nationality residuals include reclassification; combined residual is a stock difference, not migration flows",
            "limitations": [
                "Registration differs from residence",
                "Period life tables approximate cohort mortality",
                "Moves and model errors cannot be separated",
                "Sparse and estimated results require caution",
                *(
                    [
                        "Conditional zero inference requires matched complete monthly controls; raw nulls remain unchanged",
                        "Common research parent aggregates are not approved historical administrative boundaries",
                    ]
                    if config.dataset_kind == "research"
                    else []
                ),
            ],
        },
    )
    index_ref = artifact("index", index, 500000)
    default_level = (
        "district" if any(a["level"] == "district" for a in index) else "city"
    )
    indicator_refs = {}
    if config.dataset_kind == "research":
        for (level, preset), rows in sorted(by_key.items()):
            indicator_refs.setdefault(level, {})[preset] = artifact(
                f"indicators-{level}-{preset}", rows, 500000
            )
        indicator_ref = indicator_refs[default_level]["cohorts"]
    else:
        indicator_ref = artifact("indicators", indicator_rows, 500000)
    initial = index_ref["gzip_bytes"] + indicator_ref["gzip_bytes"]
    if initial > 500000:
        raise ContractError("combined initial payload exceeds 500 KB")
    commit = (
        subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
        ).stdout.strip()
        or "unknown"
    )
    code_root = Path(__file__).resolve().parents[2]
    code_hasher = hashlib.sha256()
    for source_path in sorted(
        [
            *code_root.glob("src/**/*.py"),
            *code_root.glob("web/*.js"),
            *code_root.glob("web/*.html"),
            *code_root.glob("web/*.css"),
        ]
    ):
        code_hasher.update(str(source_path.relative_to(code_root)).encode())
        code_hasher.update(source_path.read_bytes())
    manifest = {
        "schema_version": 2,
        "dataset_kind": config.dataset_kind,
        "notice": (
            "Investigación con datos municipales observados y mortalidad nacional; ceros inferidos bajo controles mensuales. No es una publicación estadística oficial."
            if config.dataset_kind == "research"
            else "Datos simulados; geometría sintética. No son estadísticas oficiales."
            if config.dataset_kind == "demonstration"
            else None
        ),
        "config": config.to_dict(),
        "start_year": config.start_year,
        "end_year": config.end_year,
        "interval_years": config.interval,
        "presets": presets,
        "default_level": default_level,
        "index": index_ref,
        "indicators": indicator_ref,
        "indicators_by_level_preset": indicator_refs,
        "geometry": geometries,
        "qa": qa_ref,
        "sources": source_ref,
        "method": metadata_ref,
        "downloads": {
            "csv": "downloads/cohort_detail.csv",
            "parquet": "downloads/cohort_detail.parquet",
        },
        "profiles": profile_refs,
        "artifacts": artifacts,
        "build_commit": commit,
        "code_sha256": code_hasher.hexdigest(),
        "release_passed": config.dataset_kind == "official" and gate["passed"],
        "performance": {"initial_gzip_bytes": initial, "budgets": budgets},
        "cache_policy": "Hashed assets: public,max-age=31536000,immutable; manifest and catalog: no-cache",
    }
    compact_research_manifest(output, manifest)
    (output / "manifest.json").write_bytes(dumps(manifest))
    (output / "audit.html").write_text(
        '<!doctype html><html lang="es"><meta charset="utf-8"><title>Auditoría</title><h1>Auditoría del conjunto</h1><p>'
        + html.escape(manifest["notice"] or "Datos oficiales")
        + "</p><h2>Validación</h2><pre>"
        + html.escape(json.dumps(qa, ensure_ascii=False, indent=2))
        + "</pre><h2>Fuentes</h2><pre>"
        + html.escape(json.dumps(sources or [], ensure_ascii=False, indent=2))
        + "</pre></html>",
        encoding="utf-8",
    )
    return manifest
