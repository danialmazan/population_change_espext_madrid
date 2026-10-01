from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


SEXES = {"male", "female"}
NATIONALITIES = {"ESP", "EXT"}
LEVELS = {"section", "barrio", "district", "city"}
BOUNDARY_STATUSES = {
    "unchanged",
    "exact_harmonisation",
    "estimated_harmonisation",
    "unreliable",
}


class ContractError(ValueError):
    """Raised when an input violates the analytical data contract."""


@dataclass(frozen=True)
class Geography:
    area_id: str
    name: str
    level: str
    parent_id: str | None
    boundary_status: str
    boundary_method: str


PopulationKey = tuple[str, int, str, str]
MortalityKey = tuple[int, int, str]


def _rows(path: str | Path, required: set[str]) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        missing = required - fields
        if missing:
            raise ContractError(f"{path}: missing columns {sorted(missing)}")
        return list(reader)


def read_population(path: str | Path) -> dict[PopulationKey, int]:
    required = {"geography_id", "age", "sex", "nationality", "population"}
    result: dict[PopulationKey, int] = {}
    for line, row in enumerate(_rows(path, required), 2):
        try:
            age = int(row["age"])
            population = int(row["population"])
        except ValueError as exc:
            raise ContractError(f"{path}:{line}: age/population must be integers") from exc
        sex, nationality = row["sex"], row["nationality"]
        if not 0 <= age <= 130 or population < 0:
            raise ContractError(f"{path}:{line}: invalid age or population")
        if sex not in SEXES or nationality not in NATIONALITIES:
            raise ContractError(f"{path}:{line}: invalid sex or nationality")
        key = (row["geography_id"], age, sex, nationality)
        if key in result:
            raise ContractError(f"{path}:{line}: duplicate population cell {key}")
        result[key] = population
    return result


def read_mortality(path: str | Path) -> dict[MortalityKey, float]:
    required = {"year", "age", "sex", "qx"}
    result: dict[MortalityKey, float] = {}
    for line, row in enumerate(_rows(path, required), 2):
        try:
            year, age, qx = int(row["year"]), int(row["age"]), float(row["qx"])
        except ValueError as exc:
            raise ContractError(f"{path}:{line}: invalid mortality value") from exc
        if row["sex"] not in SEXES or not 0 <= age <= 130 or not 0 <= qx <= 1:
            raise ContractError(f"{path}:{line}: mortality outside contract")
        key = (year, age, row["sex"])
        if key in result:
            raise ContractError(f"{path}:{line}: duplicate mortality cell {key}")
        result[key] = qx
    return result


def read_geographies(path: str | Path) -> dict[str, Geography]:
    required = {
        "area_id", "name", "level", "parent_id", "boundary_status", "boundary_method"
    }
    result: dict[str, Geography] = {}
    for line, row in enumerate(_rows(path, required), 2):
        area_id = row["area_id"]
        if not area_id or area_id in result:
            raise ContractError(f"{path}:{line}: blank or duplicate area_id")
        if row["level"] not in LEVELS or row["boundary_status"] not in BOUNDARY_STATUSES:
            raise ContractError(f"{path}:{line}: invalid level or boundary status")
        result[area_id] = Geography(
            area_id=area_id,
            name=row["name"],
            level=row["level"],
            parent_id=row["parent_id"] or None,
            boundary_status=row["boundary_status"],
            boundary_method=row["boundary_method"],
        )
    for geo in result.values():
        if geo.parent_id and geo.parent_id not in result:
            raise ContractError(f"{path}: {geo.area_id} has unknown parent {geo.parent_id}")
        seen = {geo.area_id}
        cursor = geo
        while cursor.parent_id:
            if cursor.parent_id in seen:
                raise ContractError(f"{path}: hierarchy cycle at {cursor.parent_id}")
            seen.add(cursor.parent_id)
            cursor = result[cursor.parent_id]
    return result

