"""Config-driven offline build from pinned, normalized analytical inputs."""

import json
from pathlib import Path
from .config import ModelConfig
from .acquisition import digest, verify_sources, read_lock
from .io import read_population, read_geographies, read_mortality, ContractError
from .geography import read_geometry, overlay, harmonize, assign_parents, wgs84
from .model import build_analysis
from .qa import feasibility, reconcile
from .normalize import discontinuities
from .scenarios import compare_analyses, births_counterfactual, nationality_scenarios
from .export import write_bundle


def run_project(project_path):
    project_path = Path(project_path).resolve()
    root = project_path.parent
    project = json.loads(project_path.read_text())
    config = ModelConfig(**project["model"])
    resolve = lambda name: root / project[name]
    geographies = read_geographies(resolve("geographies"))
    start = read_population(resolve("start"))
    end = read_population(resolve("end"))
    mortality = read_mortality(resolve("mortality"))
    evidence = (
        json.loads(resolve("evidence").read_text()) if project.get("evidence") else {}
    )
    for name, item in evidence.items():
        if name == "warnings":
            continue
        artifact = root / item.get("artifact", "")
        if (
            not artifact.is_file()
            or not item.get("sha256")
            or digest(artifact) != item["sha256"]
        ):
            item["passed"] = False
    # Source profile sidecars bind normalized files to audited schemas/reference dates.
    profiles = [
        json.loads((root / path).read_text())
        for path in project.get("annual_profiles", [])
    ]
    if profiles:
        reports_annual = discontinuities(profiles, config.discontinuity_threshold)
    else:
        reports_annual = []
    reports = {"annual_diagnostics": reports_annual}
    geometric = {}
    if project.get("geometry_audit"):
        spec = project["geometry_audit"]
        old = read_geometry(
            root / spec["old"], spec["crs"], spec.get("id_field", "area_id")
        )
        new = read_geometry(
            root / spec["new"], spec["crs"], spec.get("id_field", "area_id")
        )
        if set(old) != {k[0] for k in start} or set(new) != {k[0] for k in end}:
            raise ContractError("geometry and population section IDs disagree")
        review = (
            json.loads((root / spec["reviews"]).read_text())
            if spec.get("reviews")
            else {}
        )
        audit = overlay(
            old, new, config.overlap_tolerance, config.material_overlap, review
        )
        for component in audit["components"]:
            zid = component["zone_id"]
            if (
                zid not in geographies
                or geographies[zid].boundary_status != component["quality_status"]
            ):
                raise ContractError(
                    "supplied zone quality disagrees with geometry audit"
                )
        if spec.get("municipality"):
            from .geography import topology_audit
            from shapely.ops import unary_union

            municipality = unary_union(
                list(read_geometry(root / spec["municipality"], spec["crs"]).values())
            )
            audit["old_topology"] = topology_audit(
                old, config.overlap_tolerance, municipality
            )
            audit["new_topology"] = topology_audit(
                new, config.overlap_tolerance, municipality
            )
            for key in ["old_topology", "new_topology"]:
                if (
                    max(audit[key]["gap_area"], audit[key]["outside_area"])
                    > config.overlap_tolerance * municipality.area
                ):
                    raise ContractError(
                        "municipal coverage gaps/outside areas exceed topology tolerance"
                    )
        if not audit["old_topology"]["valid"] or not audit["new_topology"]["valid"]:
            raise ContractError("overlapping source polygons")
        reports["feasibility"] = feasibility(
            start,
            end,
            audit["crosswalk"],
            audit["components"],
            config.exact_coverage_gate,
        )
        for vintage, population in [("old", start), ("new", end)]:
            transformed = harmonize(
                population, [r for r in audit["crosswalk"] if r["vintage"] == vintage]
            )
            if vintage == "old":
                start = transformed
            else:
                end = transformed
        # Parent vintages must both be supplied and compared independently.
        for level in ["barrio", "district"]:
            parent = spec["parents"][level]
            assignment = assign_parents(
                audit["zones"],
                read_geometry(root / parent["old"], parent["crs"]),
                read_geometry(root / parent["new"], parent["crs"]),
                config.overlap_tolerance,
            )
            if level == "barrio":
                for zid, pid in assignment.items():
                    if zid not in geographies or geographies[zid].parent_id != pid:
                        raise ContractError(
                            "stable zone hierarchy does not match audited parent"
                        )
            else:
                for zid, pid in assignment.items():
                    if geographies[geographies[zid].parent_id].parent_id != pid:
                        raise ContractError(
                            "stable zone district differs from audited parent"
                        )
        reports["boundary_audit"] = {k: v for k, v in audit.items() if k != "zones"}
        intermediate = root / project.get("intermediate", "data/intermediate")
        intermediate.mkdir(parents=True, exist_ok=True)
        import pyarrow as pa
        import pyarrow.parquet as pq

        pq.write_table(
            pa.Table.from_pylist(
                [
                    {
                        "zone_id": gid,
                        "geometry_wkb": geom.wkb,
                        "crs": "EPSG:25830",
                        "zone_version": config.zone_version,
                    }
                    for gid, geom in audit["zones"].items()
                ]
            ),
            intermediate / "common_zones.parquet",
            compression="zstd",
        )
        pq.write_table(
            pa.Table.from_pylist(audit["crosswalk"]),
            intermediate / "geography_crosswalk.parquet",
            compression="zstd",
        )
        geometric["section"] = wgs84(audit["zones"])
    for level, spec in project.get("web_geometry", {}).items():
        geometric[level] = wgs84(
            read_geometry(
                root / spec["path"], spec["crs"], spec.get("id_field", "area_id")
            )
        )
    kwargs = dict(
        dataset_kind=config.dataset_kind,
        min_expected=config.min_expected,
        terminal_age=config.terminal_age,
    )
    analysis = build_analysis(
        start, end, mortality, geographies, config.start_year, config.end_year, **kwargs
    )
    variants = {
        "half-age": build_analysis(
            start,
            end,
            mortality,
            geographies,
            config.start_year,
            config.end_year,
            half_age=True,
            **kwargs,
        )
    }
    for label, path in project.get("mortality_variants", {}).items():
        variants[label] = build_analysis(
            start,
            end,
            read_mortality(root / path),
            geographies,
            config.start_year,
            config.end_year,
            **kwargs,
        )
    if project.get("published_totals"):
        controls = json.loads(resolve("published_totals").read_text())
        reports["reconciliation"] = {
            str(year): reconcile(
                analysis, [r for r in controls if r["year"] == year], year
            )
            for year in [config.start_year, config.end_year]
        }
        if any(
            not r["passed"] for rows in reports["reconciliation"].values() for r in rows
        ):
            raise ContractError("published totals do not reconcile")
    if project.get("survival_reference"):
        from .model import survival_probability

        independent = read_mortality(resolve("survival_reference"))
        reports["independent_survival"] = [
            {
                "age": a,
                "sex": s,
                "primary": survival_probability(
                    a, s, config.start_year, config.end_year, mortality
                ),
                "reference": survival_probability(
                    a, s, config.start_year, config.end_year, independent
                ),
            }
            for a, s in sorted(
                {
                    (k[1], k[2])
                    for k in start
                    if k[1] + config.interval < config.terminal_age
                }
            )
        ]
        if any(
            abs(r["primary"] - r["reference"])
            > project.get("survival_reference_tolerance", 1e-6)
            for r in reports["independent_survival"]
        ):
            raise ContractError("independent survival chains disagree")
    research = project.get("research", {})
    if research.get("fertility"):
        import csv

        with (root / research["fertility"]).open() as f:
            fertility = {
                (int(r["year"]), int(r["age"])): float(r["asfr_per_1000"])
                for r in csv.DictReader(f)
            }
        reports["birth_scenario"] = births_counterfactual(
            start, mortality, fertility, config.start_year, config.end_year
        )
    if research.get("nationality_hazards"):
        import csv

        with (root / research["nationality_hazards"]).open() as f:
            hazards = {
                (int(r["year"]), int(r["age"]), r["sex"]): float(r["hazard"])
                for r in csv.DictReader(f)
            }
        eligible_start = {
            k: v
            for k, v in start.items()
            if k[1] + config.interval < config.terminal_age
        }
        reports["nationality_scenarios"] = nationality_scenarios(
            eligible_start, mortality, hazards, config.start_year, config.end_year
        )
    sources = (
        verify_sources(resolve("source_lock"), resolve("raw_root"))
        if project.get("source_lock")
        else []
    )
    if config.dataset_kind == "official":
        if not sources or not all(
            r["passed"] and r["reviewed_by"] and r["license"] for r in sources
        ):
            raise ContractError(
                "official source locks missing, changed, or not reviewed/licensed"
            )
        if (
            not project.get("geometry_audit")
            or not project.get("published_totals")
            or not project.get("survival_reference")
        ):
            raise ContractError(
                "official release requires real boundary and published-total audits"
            )
        expected_dates = {
            f"{year}-01-01"
            for year in range(
                min(2014, config.start_year), max(2025, config.end_year) + 1
            )
        }
        if not expected_dates <= {p["reference_date"] for p in profiles} or not all(
            p.get("schema_reviewed") for p in profiles
        ):
            raise ContractError(
                "official release requires reviewed 2014–2025 January profiles"
            )
        if not project["geometry_audit"].get("municipality"):
            raise ContractError(
                "official boundary audit requires municipal coverage diagnostics"
            )
        controls_by_year = {
            year: {
                r["area_id"]
                for r in controls
                if r["year"] == year
                and r.get("age") is None
                and not r.get("nationality")
            }
            for year in [config.start_year, config.end_year]
        }
        required_controls = {
            gid
            for gid, geo in geographies.items()
            if geo.level in {"barrio", "district", "city"}
        }
        if any(not required_controls <= ids for ids in controls_by_year.values()):
            raise ContractError("independent totals missing for an aggregate geography")
        locked = read_lock(resolve("source_lock"))["sources"]
        for profile in profiles:
            if not any(
                s["sha256"] == profile["sha256"]
                and s.get("reference_date") == profile["reference_date"]
                for s in locked
            ):
                raise ContractError(
                    "annual profile is not bound to a pinned dated source"
                )
        if reports["feasibility"]["changed_components_pending_review"]:
            raise ContractError("changed geometry components need documented review")
    sensitivity = compare_analyses(analysis, variants)
    reports["sensitivities"] = sensitivity
    provenance = {
        name: {"path": project[name], "sha256": digest(resolve(name))}
        for name in ["start", "end", "mortality", "geographies"]
    }
    reports["timing_materiality"] = [
        r
        for r in sensitivity
        if r["scenario"] == "half-age"
        and r["relative_difference"] is not None
        and abs(r["relative_difference"]) > config.timing_materiality
    ]
    manifest = write_bundle(
        analysis,
        config,
        geographies,
        geometric,
        resolve("output"),
        evidence=evidence,
        sources={"locked_sources": sources, "analytical_inputs": provenance},
        sensitivities=sensitivity,
    )
    reports_dir = resolve("output") / "reports"
    reports_dir.mkdir(exist_ok=True)
    for name, value in reports.items():
        (reports_dir / (name + ".json")).write_text(
            json.dumps(value, indent=2, ensure_ascii=False)
        )
    manifest["default_level"] = reports.get("feasibility", {}).get(
        "recommended_level", "district"
    )
    # Every standard build emits an exact-only tier used by the default explorer.
    reliable = {
        gid
        for gid, geo in geographies.items()
        if geo.boundary_status in {"unchanged", "exact_harmonisation"}
    }
    exact_start = {k: v for k, v in start.items() if k[0] in reliable}
    exact_end = {k: v for k, v in end.items() if k[0] in reliable}
    exact_geo = {gid: geo for gid, geo in geographies.items() if gid in reliable}
    if any(
        geo.parent_id and geo.parent_id not in exact_geo for geo in exact_geo.values()
    ):
        raise ContractError("exact tier requires audited reliable parents")
    exact = build_analysis(
        exact_start,
        exact_end,
        mortality,
        exact_geo,
        config.start_year,
        config.end_year,
        **kwargs,
    )
    exact_geometry = {
        level: {gid: g for gid, g in shapes.items() if gid in exact_geo}
        for level, shapes in geometric.items()
    }
    exact_variants = {
        "half-age": build_analysis(
            exact_start,
            exact_end,
            mortality,
            exact_geo,
            config.start_year,
            config.end_year,
            half_age=True,
            **kwargs,
        )
    }
    for label, path in project.get("mortality_variants", {}).items():
        exact_variants[label] = build_analysis(
            exact_start,
            exact_end,
            read_mortality(root / path),
            exact_geo,
            config.start_year,
            config.end_year,
            **kwargs,
        )
    exact_sensitivity = compare_analyses(exact, exact_variants)
    exact_manifest = write_bundle(
        exact,
        config,
        exact_geo,
        exact_geometry,
        resolve("output") / "exact",
        evidence=evidence,
        sources={"locked_sources": sources, "analytical_inputs": provenance},
        sensitivities=exact_sensitivity,
    )
    exact_manifest["coverage_note"] = (
        "Solo zonas exactas; los agregados excluyen estimaciones y zonas no fiables. Consulta cobertura en la auditoría."
    )
    exact_manifest["default_level"] = manifest["default_level"]
    for directory, value in [
        (resolve("output"), manifest),
        (resolve("output") / "exact", exact_manifest),
    ]:
        (directory / "manifest.json").write_text(json.dumps(value, ensure_ascii=False))
    return manifest
