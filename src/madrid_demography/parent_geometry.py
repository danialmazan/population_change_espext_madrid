"""Read independent parent layers and enforce explicit temporal validity."""

from datetime import date
import io
import zipfile
from .io import ContractError


def require_parent_vintage(candidate, reference_date):
    if (
        candidate.get("temporal_validity_verified") is not True
        or not candidate.get("valid_from")
        or not candidate.get("valid_to")
        or not candidate.get("validity_evidence")
    ):
        raise ContractError(
            "Independent parent layer has no verified validity for endpoint"
        )
    try:
        start = date.fromisoformat(candidate["valid_from"])
        end = date.fromisoformat(candidate["valid_to"])
        endpoint = date.fromisoformat(reference_date)
    except (ValueError, TypeError) as exc:
        raise ContractError("Invalid parent validity date") from exc
    if not start <= endpoint <= end:
        raise ContractError(
            "Independent parent layer has no verified validity for endpoint"
        )


def canonical_parent(district, barrio=None):
    district = str(district).strip()
    if not district.isdigit() or not 1 <= int(district) <= 21:
        raise ContractError("Invalid Madrid parent district")
    d = int(district)
    if barrio is None:
        return f"{d:02d}"
    barrio = str(barrio).strip()
    if not barrio.isdigit() or int(barrio) // 10 != d or not 1 <= int(barrio) % 10 <= 9:
        raise ContractError("Parent barrio code disagrees with district")
    return f"{d:02d}{int(barrio) % 10:02d}"


def read_parent_layer(path, contract):
    import shapefile
    from pyproj import CRS
    from shapely.geometry import shape

    with zipfile.ZipFile(path) as outer:
        payload = (
            outer.read(contract["nested_archive"])
            if contract.get("nested_archive")
            else None
        )
        with (
            zipfile.ZipFile(io.BytesIO(payload))
            if payload
            else zipfile.ZipFile(path) as archive
        ):
            base = contract["layer"][:-4]
            names = {n.lower(): n for n in archive.namelist()}

            def data(extension):
                name = names.get((base + extension).lower())
                if name is None:
                    raise ContractError("Missing parent shapefile member")
                return archive.read(name)

            if not CRS.from_wkt(data(".prj").decode("ascii")).equals(
                CRS.from_epsg(25830)
            ):
                raise ContractError("Parent layer needs explicit CRS conversion")
            cpg = names.get((base + ".cpg").lower())
            if cpg and archive.read(cpg).decode().strip().upper().replace(
                "-", ""
            ) != contract["encoding"].upper().replace("-", ""):
                raise ContractError("Parent DBF encoding differs from contract")
            reader = shapefile.Reader(
                shp=io.BytesIO(data(".shp")),
                dbf=io.BytesIO(data(".dbf")),
                encoding=contract["encoding"],
            )
            geometries, labels = {}, {}
            for record in reader.iterShapeRecords():
                attrs = record.record.as_dict()
                gid = canonical_parent(
                    attrs[contract["district_field"]],
                    attrs[contract["barrio_field"]]
                    if contract.get("barrio_field")
                    else None,
                )
                geometry = shape(record.shape.__geo_interface__)
                if (
                    gid in geometries
                    or geometry.is_empty
                    or not geometry.is_valid
                    or geometry.geom_type not in ("Polygon", "MultiPolygon")
                ):
                    raise ContractError(
                        f"Invalid/duplicate independent parent polygon {gid}"
                    )
                geometries[gid] = geometry
                labels[gid] = attrs[contract["name_field"]]
            if len(geometries) != contract["expected_features"]:
                raise ContractError("Parent layer feature count differs from contract")
            return geometries, dict(
                layer=contract["layer"],
                nested_archive=contract.get("nested_archive"),
                crs="EPSG:25830",
                encoding=contract["encoding"],
                feature_count=len(geometries),
                names=labels,
                archive_member_timestamp=list(
                    archive.getinfo(names[contract["layer"].lower()]).date_time
                ),
            )


def containment_review(
    sections, parents, memberships, population, level, tolerance=0.001
):
    from shapely.ops import unary_union

    records = []
    for gid, geometry in sorted(sections.items()):
        raw_parents = memberships.get(gid, set())
        ids = sorted({p[0] if level == "district" else p[1] for p in raw_parents})
        missing = [p for p in ids if p not in parents]
        if not ids or missing:
            records.append(
                dict(
                    section_id=gid,
                    parent_ids=ids,
                    status="missing_parent",
                    known_population=population.get(gid, 0),
                )
            )
            continue
        union = unary_union([parents[p] for p in ids])
        outside = geometry.difference(union).area / geometry.area
        records.append(
            dict(
                section_id=gid,
                parent_ids=ids,
                status="contained_candidate"
                if outside <= tolerance
                else "outside_declared_parent",
                outside_area_ratio=outside,
                known_population=population.get(gid, 0),
                ambiguous_raw_parent=len(ids) > 1,
            )
        )
    return records
