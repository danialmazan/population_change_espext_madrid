"""Provisional boundary overlay; candidates require review before analytical use."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from collections import Counter
from pathlib import Path

from .acquire import load_manifest
from .profile import latest_receipt


def read_sections(path: Path) -> tuple[dict, dict]:
    import shapefile
    from pyproj import CRS
    from shapely.geometry import shape

    with zipfile.ZipFile(path) as archive:
        names = {Path(n).suffix.lower(): n for n in archive.namelist()}
        crs = CRS.from_wkt(archive.read(names[".prj"]).decode("ascii"))
        if not crs.equals(CRS.from_epsg(25830)):
            raise ValueError("expected EPSG:25830; explicit reprojection required")
        reader = shapefile.Reader(
            shp=io.BytesIO(archive.read(names[".shp"])),
            dbf=io.BytesIO(archive.read(names[".dbf"])),
            encoding="latin1",
        )
        result, invalid = {}, []
        for index, record in enumerate(reader.iterRecords()):
            attrs = record.as_dict()
            if attrs["CUMUN"] != "28079":
                continue
            code = attrs["CUSEC"]
            if code in result:
                raise ValueError(f"duplicate geometry ID {code}")
            if (
                attrs["CUDIS"] != code[:7]
                or attrs["CDIS"] != code[5:7]
                or attrs["CSEC"] != code[7:]
                or not 1 <= int(attrs["CDIS"]) <= 21
            ):
                raise ValueError(
                    f"inconsistent geometry district/section attributes {code}"
                )
            geometry = shape(reader.shape(index).__geo_interface__)
            if not geometry.is_valid or geometry.is_empty:
                invalid.append(code)
            result[code] = geometry
        return result, {
            "crs": "EPSG:25830",
            "sections": len(result),
            "invalid_or_empty_ids": invalid,
            "layer": names[".shp"],
            "district_section_attribute_checks_passed": True,
        }


def classify(old: dict, new: dict, tolerance: float = 0.001) -> dict:
    from shapely import STRtree, union_all

    valid_old = {k: g for k, g in old.items() if g.is_valid and not g.is_empty}
    valid_new = {k: g for k, g in new.items() if g.is_valid and not g.is_empty}
    new_ids = sorted(valid_new)
    new_shapes = [valid_new[k] for k in new_ids]
    tree = STRtree(new_shapes)
    graph = {("old", k): set() for k in old} | {("new", k): set() for k in new}
    ignored_area = 0.0
    for old_id, geometry in valid_old.items():
        for index in tree.query(geometry, predicate="intersects"):
            other = new_shapes[index]
            area = geometry.intersection(other).area
            if area <= max(1.0, min(geometry.area, other.area) * tolerance):
                ignored_area += area
                continue
            a, b = ("old", old_id), ("new", new_ids[index])
            graph[a].add(b)
            graph[b].add(a)
    visited, components = set(), []
    for node in sorted(graph):
        if node in visited:
            continue
        stack, component = [node], set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            stack.extend(graph[current] - component)
        visited.update(component)
        before = sorted(k for vintage, k in component if vintage == "old")
        after = sorted(k for vintage, k in component if vintage == "new")
        entry = {"old_ids": before, "new_ids": after, "status": "unreliable_candidate"}
        if (
            before
            and after
            and all(k in valid_old for k in before)
            and all(k in valid_new for k in after)
        ):
            old_union = union_all([old[k] for k in before])
            new_union = union_all([new[k] for k in after])
            intersection = old_union.intersection(new_union).area
            old_overlap, new_overlap = (
                intersection / old_union.area,
                intersection / new_union.area,
            )
            entry.update(
                old_mutual_overlap=old_overlap,
                new_mutual_overlap=new_overlap,
                symmetric_difference_m2=old_union.symmetric_difference(new_union).area,
            )
            if min(old_overlap, new_overlap) >= 1 - tolerance:
                if len(before) == len(after) == 1:
                    entry["status"] = (
                        "unchanged_candidate"
                        if before == after
                        else "renumbered_candidate"
                    )
                else:
                    entry["status"] = "exact_aggregate_candidate"
            else:
                entry["status"] = "redrawn_candidate"
        components.append(entry)
    old_union, new_union = (
        union_all(list(valid_old.values())),
        union_all(list(valid_new.values())),
    )
    return {
        "status": "provisional_requires_review",
        "tolerance": tolerance,
        "minimum_material_overlap_m2": 1.0,
        "ignored_intersection_area_m2": ignored_area,
        "component_counts": dict(Counter(c["status"] for c in components)),
        "old_internal_overlap_m2": sum(g.area for g in valid_old.values())
        - old_union.area,
        "new_internal_overlap_m2": sum(g.area for g in valid_new.values())
        - new_union.area,
        "municipal_symmetric_difference_m2": old_union.symmetric_difference(
            new_union
        ).area,
        "components": components,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("sources.lock.yml"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--profiles", type=Path, default=Path("docs/audit/padron_profiles.json")
    )
    parser.add_argument(
        "--report", type=Path, default=Path("docs/audit/boundaries.json")
    )
    args = parser.parse_args()
    sources = {s["id"]: s for s in load_manifest(args.manifest)["sources"]}
    geometries, metadata = {}, {}
    for year in (2015, 2025):
        receipt = latest_receipt(args.raw_dir, sources[f"sections_{year}"])
        if not receipt or receipt["status"] == "failed":
            raise ValueError(f"missing successful sections_{year} acquisition")
        path = Path(receipt["path"])
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        if checksum != receipt["sha256"] or sources[f"sections_{year}"].get(
            "sha256"
        ) not in (None, checksum):
            raise ValueError(f"sections_{year} checksum mismatch")
        geometries[year], metadata[year] = read_sections(path)
        metadata[year]["sha256"] = receipt["sha256"]
    report = classify(geometries[2015], geometries[2025])
    report.update(vintages=metadata, production_ready=False)
    profiles = {
        p["source_id"]: p for p in json.loads(args.profiles.read_text())["profiles"]
    }
    coverage = {}
    for year, key in ((2015, "old_ids"), (2025, "new_ids")):
        profile = profiles[f"padron_january_{year}"]
        populations = {
            "28079" + f"{int(code) // 1000:02d}{int(code) % 1000:03d}": count
            for code, count in profile["known_population_by_section"].items()
        }
        candidate_ids = {
            code
            for c in report["components"]
            for code in c[key]
            if c["status"]
            in (
                "unchanged_candidate",
                "renumbered_candidate",
                "exact_aggregate_candidate",
            )
        }
        covered = sum(populations.get(code, 0) for code in candidate_ids)
        coverage[year] = {
            "candidate_known_population_share": covered
            / profile["known_population_sum"],
            "known_population_missing_section_code": profile.get(
                "invalid_geography_known_population", 0
            ),
            "known_population_with_geometry": sum(
                v for k, v in populations.items() if k in geometries[year]
            ),
            "population_ids_without_geometry": sorted(
                set(populations) - set(geometries[year])
            ),
            "geometry_ids_without_population": sorted(
                set(geometries[year]) - set(populations)
            ),
        }
    report["population_coverage"] = coverage
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {"components": report["component_counts"], "coverage": coverage}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
