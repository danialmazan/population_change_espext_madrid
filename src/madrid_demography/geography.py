"""Projected geometry audits, stable overlap components and reviewed allocation."""

from collections import defaultdict
import math
from pathlib import Path
import json
from pyproj import Transformer
from shapely.geometry import shape, mapping
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree
from .io import ContractError


def read_geometry(path, crs, id_field="area_id"):
    transformer = Transformer.from_crs(crs, "EPSG:25830", always_xy=True)
    result = {}
    for feature in json.loads(Path(path).read_text())["features"]:
        gid = str(feature["properties"][id_field])
        geom = transform(transformer.transform, shape(feature["geometry"]))
        if (
            gid in result
            or geom.is_empty
            or not geom.is_valid
            or geom.geom_type not in {"Polygon", "MultiPolygon"}
        ):
            raise ContractError(
                f"invalid/duplicate polygon {gid}; repairs require separately documented originals"
            )
        result[gid] = geom
    if not result:
        raise ContractError("empty geometry vintage")
    return result


def topology_audit(polygons, tolerance=0.001, municipality=None):
    ids, geometries = list(polygons), list(polygons.values())
    tree = STRtree(geometries)
    overlaps = []
    for i, geom in enumerate(geometries):
        for j in tree.query(geom, predicate="intersects"):
            j = int(j)
            if j <= i:
                continue
            area = geom.intersection(geometries[j]).area
            if area > tolerance * min(geom.area, geometries[j].area):
                overlaps.append({"ids": [ids[i], ids[j]], "overlap_area": area})
    union = unary_union(geometries)
    return {
        "valid": not overlaps,
        "overlaps": overlaps,
        "union_area": union.area,
        "gap_area": municipality.difference(union).area
        if municipality is not None
        else None,
        "outside_area": union.difference(municipality).area
        if municipality is not None
        else None,
    }


def overlay(old, new, tolerance=0.001, material=1e-6, reviews=None):
    """Use all material overlaps; exact weights only if both component unions agree."""
    reviews = reviews or {}
    new_ids = list(new)
    new_shapes = list(new.values())
    tree = STRtree(new_shapes)
    graph = defaultdict(set)
    metrics = []
    for oid, geom in old.items():
        graph[("old", oid)]
        for index in tree.query(geom, predicate="intersects"):
            nid = new_ids[int(index)]
            other = new[nid]
            area = geom.intersection(other).area
            if area <= material * min(geom.area, other.area):
                continue
            graph[("old", oid)].add(("new", nid))
            graph[("new", nid)].add(("old", oid))
            metrics.append(
                {
                    "old_id": oid,
                    "new_id": nid,
                    "area": area,
                    "old_share": area / geom.area,
                    "new_share": area / other.area,
                }
            )
    for nid in new:
        graph[("new", nid)]
    visited, components, crosswalk, zones = set(), [], [], {}
    for node in sorted(graph):
        if node in visited:
            continue
        pending, component = [node], set()
        while pending:
            item = pending.pop()
            if item in component:
                continue
            component.add(item)
            pending.extend(graph[item] - component)
        visited.update(component)
        before = sorted(gid for vintage, gid in component if vintage == "old")
        after = sorted(gid for vintage, gid in component if vintage == "new")
        union0 = unary_union([old[g] for g in before])
        union1 = unary_union([new[g] for g in after])
        symmetric = union0.symmetric_difference(union1).area / max(
            union0.area, union1.area, 1e-12
        )
        compatible = bool(before and after and symmetric <= tolerance)
        if not before:
            classification = "extra"
        elif not after:
            classification = "missing"
        elif len(before) == len(after) == 1:
            classification = (
                "unchanged"
                if compatible and before == after
                else "renumbered"
                if compatible
                else "materially_redrawn"
            )
        elif len(before) == 1:
            classification = "split"
        elif len(after) == 1:
            classification = "merged"
        else:
            classification = "materially_redrawn"
        zid = (
            after[0]
            if classification == "unchanged"
            else "Z-"
            + __import__("hashlib")
            .sha256("|".join(before + after).encode())
            .hexdigest()[:12]
        )
        status = (
            "unchanged"
            if classification == "unchanged"
            else "exact_harmonisation"
            if compatible
            else "unreliable"
        )
        review = reviews.get(zid)
        components.append(
            {
                "zone_id": zid,
                "old_ids": before,
                "new_ids": after,
                "classification": classification,
                "symmetric_difference_ratio": symmetric,
                "quality_status": status,
                "review": review,
                "requires_review": classification != "unchanged" and not review,
            }
        )
        zones[zid] = union1 if after else union0
        for vintage, ids in [("old", before), ("new", after)]:
            for gid in ids:
                crosswalk.append(
                    {
                        "vintage": vintage,
                        "source_id": gid,
                        "zone_id": zid,
                        "weight": 1.0,
                        "quality_status": status,
                        "weight_basis": "exact_union"
                        if compatible
                        else "excluded_union",
                        "boundary_method": "unchanged"
                        if status == "unchanged"
                        else "exact_aggregate"
                        if compatible
                        else "excluded",
                        "review": review,
                    }
                )
    return {
        "components": components,
        "overlaps": metrics,
        "crosswalk": crosswalk,
        "zones": zones,
        "old_topology": topology_audit(old, tolerance),
        "new_topology": topology_audit(new, tolerance),
    }


def validate_crosswalk(rows, source_ids):
    grouped = defaultdict(list)
    for row in rows:
        weight = row["weight"]
        if not math.isfinite(weight) or not 0 <= weight <= 1:
            raise ContractError("invalid crosswalk weight")
        if row["quality_status"] in {
            "unchanged",
            "exact_harmonisation",
        } and weight not in {0, 1}:
            raise ContractError("fractional exact weight")
        if row["quality_status"] == "estimated_harmonisation" and (
            not row.get("review")
            or row.get("weight_basis")
            not in {"residential_capacity", "building_population"}
        ):
            raise ContractError(
                "estimated allocation requires reviewed temporal residential evidence"
            )
        grouped[row["source_id"]].append(row)
    if set(grouped) != set(source_ids):
        raise ContractError("population/geometry crosswalk IDs differ")
    for gid, weights in grouped.items():
        if len({r["zone_id"] for r in weights}) != len(weights):
            raise ContractError("duplicate crosswalk destination")
        if abs(sum(r["weight"] for r in weights) - 1) > 1e-9:
            raise ContractError(f"crosswalk mass loss for {gid}")


def harmonize(population, rows):
    validate_crosswalk(rows, {key[0] for key in population})
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["source_id"]].append(row)
    result = defaultdict(float)
    for (gid, age, sex, nationality), count in population.items():
        for row in grouped[gid]:
            result[(row["zone_id"], age, sex, nationality)] += count * row["weight"]
    if abs(sum(result.values()) - sum(population.values())) > 1e-6:
        raise ContractError("harmonisation changes population")
    return dict(result)


def assign_parents(zones, old_parents, new_parents, tolerance=0.001):
    """Never infer historical membership from a current code."""
    assignment = {}
    for zid, zone in zones.items():
        possible = []
        for pid in sorted(set(old_parents) & set(new_parents)):
            old, new = old_parents[pid], new_parents[pid]
            equal = (
                old.symmetric_difference(new).area / max(old.area, new.area)
                <= tolerance
            )
            nested = (
                max(zone.difference(old).area, zone.difference(new).area) / zone.area
                <= tolerance
            )
            if equal and nested:
                possible.append(pid)
        if len(possible) != 1:
            raise ContractError(f"{zid}: requires harmonised parent; found {possible}")
        assignment[zid] = possible[0]
    return assignment


def capacity_weights(source, targets, buildings, vintage, reviews):
    """Allocation sensitivity versus land area; unsuitable temporal evidence fails."""
    if not reviews or any(
        b["vintage"] != vintage or not b.get("license") for b in buildings
    ):
        raise ContractError(
            "residential allocation requires matching vintage, licence, and review"
        )
    values, areas = {}, {}
    for gid, target in targets.items():
        clip = source.intersection(target)
        areas[gid] = clip.area
        values[gid] = sum(
            b["capacity"] * b["geometry"].intersection(clip).area / b["geometry"].area
            for b in buildings
        )
    total, area = sum(values.values()), sum(areas.values())
    if total <= 0 or area <= 0:
        raise ContractError("no residential capacity in allocation zone")
    if source.difference(unary_union(list(targets.values()))).area / source.area > 1e-6:
        raise ContractError("allocation targets do not cover source")
    weights = {gid: value / total for gid, value in values.items()}
    return weights, {gid: weights[gid] - areas[gid] / area for gid in weights}


def wgs84(polygons):
    converter = Transformer.from_crs("EPSG:25830", "EPSG:4326", always_xy=True)
    return {gid: transform(converter.transform, geom) for gid, geom in polygons.items()}


def feature_collection(polygons):
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"area_id": gid},
                "geometry": mapping(geom),
            }
            for gid, geom in sorted(polygons.items())
        ],
    }


def import_gis(source, output, layer, id_field, prefix="28079"):
    """Convert an official GDAL-readable archive/layer; preserve originals separately."""
    import subprocess
    import tempfile

    if not id_field.replace("_", "").isalnum() or not prefix.isdigit():
        raise ContractError("invalid GIS selection")
    source = Path(source).resolve()
    output = Path(output)
    input_path = "/vsizip/" + str(source) if source.suffix == ".zip" else str(source)
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / "projected.geojson"
        subprocess.run(
            [
                "ogr2ogr",
                "-f",
                "GeoJSON",
                str(target),
                input_path,
                layer,
                "-t_srs",
                "EPSG:25830",
                "-where",
                f"{id_field} LIKE '{prefix}%'",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(target.read_text())
        for feature in data["features"]:
            feature["properties"]["area_id"] = str(feature["properties"][id_field])
        if not data["features"]:
            raise ContractError("GIS selection contains no Madrid features")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(data))
    return {
        "source": str(source),
        "layer": layer,
        "id_field": id_field,
        "prefix": prefix,
        "crs": "EPSG:25830",
        "output": str(output),
        "features": len(data["features"]),
    }
