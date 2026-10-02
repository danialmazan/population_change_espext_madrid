"""Corroborate raw parent changes without silently repairing official date errors."""

from datetime import date
from .io import ContractError
from .parent_geometry import canonical_parent


def registry_date(value):
    if value == "" or value is None:
        return dict(raw="", status="missing", iso=None, year=None)
    if type(value) is float:
        if not value.is_integer():
            raise ContractError("Nonintegral registry date")
        value = int(value)
    raw = str(value).strip()
    if len(raw) != 8 or not raw.isdigit() or not 1900 <= int(raw[:4]) <= 2100:
        raise ContractError("Unrecognised registry date encoding")
    year = int(raw[:4])
    try:
        parsed = date(year, int(raw[4:6]), int(raw[6:]))
    except ValueError:
        return dict(raw=raw, status="invalid_date_year_only", iso=None, year=year)
    return dict(raw=raw, status="valid", iso=parsed.isoformat(), year=year)


def parent_at_endpoint(current, old, modification, endpoint):
    target = date.fromisoformat(endpoint)
    if old is None:
        return current, "no_previous_parent_recorded"
    if modification["status"] == "valid":
        return (
            old if target < date.fromisoformat(modification["iso"]) else current
        ), "dated_reassignment"
    if modification["status"] == "invalid_date_year_only":
        if target.year < modification["year"]:
            return old, "year_bracket_only"
        if target.year > modification["year"]:
            return current, "year_bracket_only"
    return None, "unresolved_modification_date"


def read_registry(path):
    import xlrd

    book = xlrd.open_workbook(path)
    if book.nsheets != 1:
        raise ContractError("Unreviewed section-history workbook sheets")
    sheet = book.sheet_by_index(0)
    expected = [
        "Distrito",
        "Barrio",
        "Sección",
        "Fecha de Alta",
        "Procedencia",
        "Fecha de Baja",
        "Destino",
        "Fecha de modificación",
        "Barrio antiguo",
        "Observaciones",
    ]
    if (
        sheet.row_values(3) != expected
        or sheet.cell_value(2, 0) != "1. Historia del seccionado 1988 - 2024"
    ):
        raise ContractError("Unreviewed section-history workbook schema")
    records = []
    for i in range(4, sheet.nrows):
        row = sheet.row_values(i)
        if not isinstance(row[0], (int, float)):
            continue
        d, b, section = (int(v) for v in row[:3])
        parent = canonical_parent(d, b)
        old = canonical_parent(d, int(row[8])) if row[8] != "" else None
        if not 1 <= section <= 999:
            raise ContractError("Invalid registry section")
        records.append(
            dict(
                row_number=i + 1,
                section_id=f"28079{d:02d}{section:03d}",
                parent=parent,
                previous_parent=old,
                created=registry_date(row[3]),
                closed=registry_date(row[5]),
                modified=registry_date(row[7]),
                origin=str(row[4]),
                destination=str(row[6]),
                notes=str(row[9]),
            )
        )
    return records, dict(
        sheet=sheet.name, title=sheet.cell_value(2, 0), records=len(records)
    )


def compare_registry(records, membership, endpoint):
    active = {}
    unresolved = []
    for record in records:
        start, end = record["created"], record["closed"]
        if start["status"] != "valid" or end["status"] not in ("valid", "missing"):
            unresolved.append(record["row_number"])
            continue
        if start["iso"] > endpoint or (end["iso"] and end["iso"] <= endpoint):
            continue
        parent, basis = parent_at_endpoint(
            record["parent"], record["previous_parent"], record["modified"], endpoint
        )
        if parent is None:
            unresolved.append(record["row_number"])
            continue
        active.setdefault(record["section_id"], set()).add(parent)
    matches = 0
    differences = []
    for gid, raw in sorted(membership.items()):
        actual = {b for d, b in raw}
        documented = active.get(gid, set())
        if actual == documented:
            matches += 1
        else:
            differences.append(
                dict(
                    section_id=gid,
                    raw_parents=sorted(actual),
                    registry_parents=sorted(documented),
                )
            )
    return dict(
        endpoint=endpoint,
        active_registry_sections=len(active),
        matching_raw_section_memberships=matches,
        differences=differences,
        unresolved_registry_rows=unresolved,
        registry_only_section_ids=sorted(set(active) - set(membership)),
    )
