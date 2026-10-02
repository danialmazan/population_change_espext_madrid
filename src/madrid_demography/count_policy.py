"""Conditional zero inference from exhaustive, matching monthly count controls."""

import csv
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path
from .profile import COUNTS
from .io import ContractError

BANK_KEYS = dict(
    zip(COUNTS, ["NHombresNac", "NMujeresNac", "NHombresExt", "NMujeresExt"])
)


def verify_group_counts(known, controls, expected_keys):
    if set(controls) != expected_keys or set(known) != expected_keys:
        raise ContractError("Incomplete or unexpected district/age/count coverage")
    for key in expected_keys:
        for value in (known[key], controls[key]):
            if type(value) is not int or value < 0:
                raise ContractError("Controls require nonnegative integer counts")
        if known[key] != controls[key]:
            raise ContractError(f"Monthly control mismatch: {key}")
    return len(expected_keys)


def load_controls(policy):
    controls = {}
    for evidence in policy["controls"]:
        compressed = Path(evidence["path"]).read_bytes()
        raw = gzip.decompress(compressed)
        if hashlib.sha256(raw).hexdigest() != evidence["sha256"]:
            raise ContractError("Monthly control checksum changed")
        receipt = json.loads(Path(evidence["receipt"]).read_text())
        request = receipt["request"]
        if (
            receipt["sha256"] != evidence["sha256"]
            or receipt["method"] != "POST"
            or receipt["url"] != policy["control_url"]
            or request["numSerie"] != "0301000000001"
            or request["anioSeleccion"] != "2015"
            or request["mesSeleccion"] != "1"
            or request["listaEdades"] != [str(a) for a in range(90)]
            or request["listaIdsBarrios"] != ["00 TODOS"]
            or request["listaSexos"] != ["Total"]
            or request["listaNacionalidades"] != ["Total"]
            or request["tiposDato"] != "Valores Absolutos"
            or request["accionFormulario"] != "consultarDatosBarrio"
        ):
            raise ContractError("Control request does not match policy scope")
        response = json.loads(raw.decode(receipt["response_encoding"]))
        filters = response["mapaEpigrafesFiltros"]
        if (
            response.get("status") != "success"
            or response.get("errorTitulo")
            or filters.get("Año: ") != "2015"
            or filters.get("Mes (datos a primer día del mes): ") != "Enero"
        ):
            raise ContractError("Incomplete or wrong-date monthly response")
        districts = {int(d) for d in request["listaIdsDistritos"]}
        batch_keys = set()
        for row in response["listaConsulta"]:
            district, age = int(row["distrito"]["VCodigo"]), int(row["VEdad"])
            for column, bank_key in BANK_KEYS.items():
                key = (district, age, column)
                if key in controls:
                    raise ContractError("Duplicate monthly control cell")
                controls[key] = row[bank_key]
                batch_keys.add(key)
        expected = {(d, a, c) for d in districts for a in range(90) for c in COUNTS}
        if batch_keys != expected:
            raise ContractError("Monthly response coverage differs from request")
    return controls


def validate_policy(policy, source, raw_path):
    if (
        policy["id"] != "monthly-2015-eligible-zero-v1"
        or policy["production_ready"] is not False
        or policy["reference_date"] != "2015-01-01"
        or policy["age_min"] != 0
        or policy["age_max"] != 89
        or source["id"] != policy["source_id"]
        or source["reference_date"] != policy["reference_date"]
        or source["sha256"] != policy["source_sha256"]
    ):
        raise ContractError("Unsupported policy or source scope")
    if (
        hashlib.sha256(Path(raw_path).read_bytes()).hexdigest()
        != policy["source_sha256"]
    ):
        raise ContractError("Population source checksum changed")
    controls = load_controls(policy)
    known, blanks = Counter(), Counter()
    with Path(raw_path).open(encoding=source["encoding"], newline="") as handle:
        for row in csv.DictReader(handle, delimiter=source["delimiter"]):
            row = {k.strip().upper(): v.strip() for k, v in row.items()}
            label = row["COD_EDAD_INT"]
            if not label.isdigit() or not 0 <= int(label) <= 89:
                continue
            for column in COUNTS:
                key = (int(row["COD_DISTRITO"]), int(label), column)
                value = row[column]
                if value and not value.isdigit():
                    raise ContractError("Invalid raw count in policy scope")
                known[key] += int(value) if value else 0
                blanks[key] += value == ""
    expected = {(d, a, c) for d in range(1, 22) for a in range(90) for c in COUNTS}
    verified = verify_group_counts(known, controls, expected)
    return dict(
        verified_control_cells=verified,
        inferred_zero_cells=sum(blanks.values()),
        eligible_known_population=sum(known.values()),
    )


def export_candidate(input_path, expected_sha, output_path, policy, expected_blanks):
    """Retain raw status; zero only eligible, source-bound audit cells."""
    if hashlib.sha256(Path(input_path).read_bytes()).hexdigest() != expected_sha:
        raise ContractError("Audit export checksum changed")
    inferred = 0
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = output_path.with_suffix(".pending")
    try:
        with (
            Path(input_path).open(newline="") as handle,
            staging.open("w", newline="") as out,
        ):
            reader = csv.DictReader(handle)
            writer = csv.DictWriter(
                out,
                fieldnames=reader.fieldnames
                + ["raw_population_status", "count_policy_id"],
            )
            writer.writeheader()
            for row in reader:
                if (
                    row["source_sha256"] != policy["source_sha256"]
                    or row["reference_date"] != policy["reference_date"]
                ):
                    raise ContractError("Audit row provenance differs from policy")
                row["raw_population_status"] = row["population_status"]
                row["count_policy_id"] = ""
                if (
                    row["population_status"] == "unknown_blank"
                    and row["cohort_status"] == "eligible"
                ):
                    if (
                        not row["age"].isdigit()
                        or not 0 <= int(row["age"]) <= 89
                        or row["population"] != ""
                    ):
                        raise ContractError("Invalid inferred cell scope")
                    row["population"] = "0"
                    row["population_status"] = "inferred_zero_monthly_control"
                    row["count_policy_id"] = policy["id"]
                    inferred += 1
                writer.writerow(row)
        if inferred != expected_blanks:
            raise ContractError("Inferred cell count differs from verified raw blanks")
        staging.replace(output_path)
    finally:
        staging.unlink(missing_ok=True)
    return dict(
        inferred_zero_cells=inferred,
        output_sha256=hashlib.sha256(output_path.read_bytes()).hexdigest(),
        output_path=str(output_path),
    )
