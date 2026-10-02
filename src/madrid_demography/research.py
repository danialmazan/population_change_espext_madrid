"""Source-bound research aggregation, mortality schedules and independent checks."""

import csv
import gzip
import hashlib
import json
import math
import re
from collections import Counter
from decimal import Decimal, localcontext
from pathlib import Path

from .count_policy import BANK_KEYS
from .io import ContractError
from .profile import COUNTS

SEX = {"Hombres": "male", "Mujeres": "female"}
COUNT_KEYS = {
    "ESPANOLESHOMBRES": ("male", "ESP"),
    "ESPANOLESMUJERES": ("female", "ESP"),
    "EXTRANJEROSHOMBRES": ("male", "EXT"),
    "EXTRANJEROSMUJERES": ("female", "EXT"),
}


def pinned_path(source, root=Path("data/raw")):
    path = root / source["id"] / source["sha256"]
    if (
        path.stat().st_size != source["bytes"]
        or hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]
    ):
        raise ContractError("Changed pinned research input")
    return path


def monthly_control(year, kind, root=Path("docs/audit/research-controls")):
    stem = f"{year}-{kind}"
    receipt = json.loads((root / (stem + ".receipt.json")).read_text())
    raw = gzip.decompress((root / (stem + ".json.gz")).read_bytes())
    request = receipt["request"]
    if (
        hashlib.sha256(raw).hexdigest() != receipt["sha256"]
        or request["anioSeleccion"] != str(year)
        or request["mesSeleccion"] != "1"
        or request["listaIdsDistritos"] != ["00 TODOS"]
        or request["listaIdsBarrios"] != ["00 TODOS"]
        or request["listaSexos"] != ["Total"]
        or request["listaNacionalidades"] != ["Total"]
        or request["tiposDato"] != "Valores Absolutos"
        or request["listaEdades"]
        != ([str(a) for a in range(100)] if kind == "ages" else ["00 TODOS"])
    ):
        raise ContractError("Research monthly control scope/hash differs")
    response = json.loads(raw.decode(receipt["response_encoding"]))
    if (
        response.get("status") != "success"
        or response.get("errorTitulo")
        or response["mapaEpigrafesFiltros"].get("Año: ") != str(year)
        or response["mapaEpigrafesFiltros"].get("Mes (datos a primer día del mes): ")
        != "Enero"
    ):
        raise ContractError("Wrong-date or incomplete research control")
    records = response["listaConsulta"]
    if len(records) != (100 if kind == "ages" else 1):
        raise ContractError("Incomplete research control coverage")
    values = {}
    for record in records:
        age = int(record["VEdad"]) if kind == "ages" else "total"
        for column, bank in BANK_KEYS.items():
            value = record[bank]
            key = (age, column)
            if key in values or type(value) is not int or value < 0:
                raise ContractError("Invalid/duplicate monthly control")
            values[key] = value
    expected = {
        (a, c) for a in (range(100) if kind == "ages" else ["total"]) for c in COUNTS
    }
    if set(values) != expected:
        raise ContractError("Research control age coverage differs")
    return values, receipt["sha256"]


def read_research_population(source, zone_map=None, *, require_matching_controls=True):
    year = int(source["reference_date"][:4])
    city, spatial, age_sums, totals, diagnostics = (
        Counter(),
        Counter(),
        Counter(),
        Counter(),
        Counter(),
    )
    blanks = Counter()
    invalid_age = 0
    rows = 0
    unmapped = 0
    seen = set()
    with pinned_path(source).open(encoding=source["encoding"], newline="") as handle:
        for raw in csv.DictReader(handle, delimiter=source["delimiter"]):
            row = {k.strip().upper(): v.strip() for k, v in raw.items()}
            rows += 1
            district = int(row["COD_DISTRITO"])
            barrio = int(row["COD_DIST_BARRIO"]) if row["COD_DIST_BARRIO"] else 0
            section = row["COD_DIST_SECCION"]
            if not 1 <= district <= 21 or (
                section and int(section) // 1000 != district
            ):
                raise ContractError("Research geography codes differ")
            gid = f"28079{district:02d}{int(section) % 1000:03d}" if section else ""
            label = row["COD_EDAD_INT"]
            grain = (district, barrio, section, label)
            if grain in seen:
                raise ContractError("Duplicate full-grain research row")
            seen.add(grain)
            for date_field in ("FX_DATOS_INI", "FX_DATOS_FIN"):
                if date_field in row and row[date_field].replace("-", "") != source[
                    "reference_date"
                ].replace("-", ""):
                    raise ContractError("Research raw reference date differs")
            age = int(label) if label.isdigit() else 100 if label == "100 o +" else None
            valid = age is not None and 0 <= age <= 130
            for column, (sex, nat) in COUNT_KEYS.items():
                value = row[column]
                if value and not value.isdigit():
                    raise ContractError("Invalid research population count")
                count = int(value) if value else 0
                totals[column] += count
                blanks[column] += value == ""
                if age is not None and age < 100:
                    age_sums[(age, column)] += count
                diagnostics[(f"{district:02d}", f"{barrio:04d}")] += count
                if not valid:
                    invalid_age += count
                    continue
                analytical_age = min(age, 100)
                city[("MAD", analytical_age, sex, nat)] += count
                if zone_map is not None:
                    if gid in zone_map:
                        spatial[(zone_map[gid], analytical_age, sex, nat)] += count
                    else:
                        unmapped += count
    ages, age_hash = monthly_control(year, "ages")
    full, total_hash = monthly_control(year, "total")
    age_differences = {
        f"{a}:{c}": age_sums[(a, c)] - v
        for (a, c), v in ages.items()
        if age_sums[(a, c)] != v
    }
    total_differences = {c: totals[c] - full[("total", c)] for c in COUNTS}
    matched = not age_differences and not any(total_differences.values())
    if require_matching_controls and age_differences:
        raise ContractError(f"{year}: age/sex/nationality control discrepancy")
    if require_matching_controls and any(total_differences.values()):
        raise ContractError(f"{year}: full monthly total discrepancy")
    report = {
        "source_id": source["id"],
        "source_sha256": source["sha256"],
        "year": year,
        "rows": rows,
        "known_total": sum(totals.values()),
        "modelled_observed_stock": sum(city.values()),
        "invalid_age_known_population": invalid_age,
        "conditionally_inferred_blank_cells": sum(blanks.values()) if matched else 0,
        "raw_blank_cells": sum(blanks.values()),
        "monthly_controls_matched": matched,
        "age_control_differences": age_differences,
        "full_total_differences": total_differences,
        "age_control_cells": 400,
        "age_control_sha256": age_hash,
        "total_control_sha256": total_hash,
        "unmapped_known_population": unmapped,
        "policy": "conditional_zero_matching_exhaustive_monthly_controls; raw inputs unchanged"
        if matched
        else "unknown_null; raw known sums are diagnostics only",
        "assumptions": [
            "same complete population universe",
            "nonnegative counts",
            "known cells correct and no compensating source errors",
        ],
        "production_ready": False,
    }
    return dict(city), dict(spatial), diagnostics, report


def number(text):
    return Decimal(text.replace(".", "").replace(",", "."))


def national_schedules(source, start=2014, end=2025):
    risks, lives = {}, {}
    with pinned_path(source).open(encoding="utf-8-sig", newline="") as handle:
        for r in csv.DictReader(handle, delimiter=";"):
            if r["Sexo"] not in SEX or r["Funciones"] not in (
                "Riesgo de muerte",
                "Supervivientes",
            ):
                continue
            y = int(r["Periodo"])
            m = re.fullmatch(r"(\d+) años?", r["Edad"])
            open100 = r["Edad"] == "100 y más años"
            if (not m and not open100) or not start <= y < end:
                continue
            a = 100 if open100 else int(m[1])
            key = (y, a, SEX[r["Sexo"]])
            target = risks if r["Funciones"] == "Riesgo de muerte" else lives
            if key in target:
                raise ContractError("Duplicate national life-table cell")
            target[key] = number(r["Total"]) / (1000 if target is risks else 1)
    required = {
        (y, a, s)
        for y in range(start, end)
        for a in range(100)
        for s in ("male", "female")
    }
    if (
        not required <= risks.keys()
        or not {
            (y, a, s)
            for y in range(start, end)
            for a in range(101)
            for s in ("male", "female")
        }
        <= lives.keys()
    ):
        raise ContractError("National qx/lx coverage incomplete")
    qx = {k: float(risks[k]) for k in required}
    lx_qx = {}
    for y, a, s in required:
        if lives[(y, a, s)] <= 0:
            raise ContractError("Invalid lx denominator")
        lx_qx[(y, a, s)] = float(1 - lives[(y, a + 1, s)] / lives[(y, a, s)])
    if any(not 0 <= q <= 1 for q in [*qx.values(), *lx_qx.values()]):
        raise ContractError("Invalid national life-table probability")
    return qx, lx_qx, lives


def calibrate_band(national, regional_nqx):
    if not 0 <= regional_nqx < 1 or any(not 0 <= q < 1 for q in national):
        raise ContractError("Invalid closed-band mortality")
    hazards = [-math.log1p(-q) for q in national]
    total = sum(hazards)
    target = -math.log1p(-regional_nqx)
    if total == 0:
        if target:
            raise ContractError("Cannot calibrate zero national hazard")
        return [0.0] * len(national)
    return [-math.expm1(-h * target / total) for h in hazards]


def regional_sensitivity(source, national):
    result = {}
    bands = 0
    with pinned_path(source).open(encoding="utf-8-sig", newline="") as handle:
        for r in csv.DictReader(handle, delimiter=";"):
            if (
                r["Comunidades y Ciudades Autónomas"] != "13 Madrid, Comunidad de"
                or r["Sexo"] not in SEX
                or r["Funciones"] != "Riesgo de muerte"
            ):
                continue
            year = int(r["Periodo"])
            sex = SEX[r["Sexo"]]
            if not 2014 <= year <= 2024:
                continue
            label = r["Edad"]
            m = re.fullmatch(r"De (\d+) a (\d+) años", label)
            ages = (
                list(range(int(m[1]), int(m[2]) + 1))
                if m
                else [0]
                if label == "0 años"
                else []
            )
            if not ages:
                continue  # Open ages are not converted to invented annual risks.
            converted = calibrate_band(
                [national[(year, a, sex)] for a in ages],
                float(number(r["Total"]) / 1000),
            )
            for age, qx in zip(ages, converted):
                if (year, age, sex) in result:
                    raise ContractError("Duplicate Madrid band")
                result[(year, age, sex)] = qx
            bands += 1
    expected = {
        (y, a, s)
        for y in range(2014, 2025)
        for a in range(95)
        for s in ("male", "female")
    }
    if set(result) != expected:
        raise ContractError("Closed-band Madrid sensitivity coverage incomplete")
    return result, {
        "closed_bands": bands,
        "method": "national single-age hazard pattern scaled so each closed-band product matches Madrid nqx",
        "approximation": True,
        "maximum_endpoint_age": 94,
        "open_groups_not_expanded": True,
    }


def independent_expected(start, lives, start_year, end_year, terminal):
    """Decimal annual count propagation from lx; no production survival helper."""
    result = {}
    with localcontext() as context:
        context.prec = 40
        for (gid, age, sex, nat), count in start.items():
            final = age + end_year - start_year
            if final >= terminal:
                continue
            remaining = Decimal(count)
            for year in range(start_year, end_year):
                current_age = age + year - start_year
                remaining = (
                    remaining
                    * lives[(year, current_age + 1, sex)]
                    / lives[(year, current_age, sex)]
                )
            result[(gid, final, sex, nat)] = float(remaining)
    return result
