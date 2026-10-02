"""Materialize audited raw sources into canonical facts for a configured build."""

import csv
import json
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from .acquisition import read_lock, digest
from .normalize import normalize_padron, extract_ine_series
from .geography import import_gis
from .io import ContractError


def prepare_project(path):
    path = Path(path).resolve()
    root = path.parent
    project = json.loads(path.read_text())
    lock = {s["id"]: s for s in read_lock(root / project["source_lock"])["sources"]}
    raw = root / project["raw_root"]

    def source_path(sid):
        source = lock[sid]
        file = raw / sid / str(source["sha256"])
        if (
            not file.exists()
            or digest(file) != source["sha256"]
            or file.stat().st_size != source["bytes"]
        ):
            raise ContractError(f"{sid}: immutable source missing or checksum mismatch")
        return file

    schemas = {
        s["schema_version"]: s
        for s in json.loads((root / project["schemas"]).read_text())["schemas"]
    }
    outputs = []
    for entry in project.get("source_ingestion", {}).get("padron", []):
        schema = schemas[entry["schema"]]
        source = lock[entry["source_id"]]
        if source.get("reference_date") != entry["reference_date"]:
            raise ContractError("ingestion reference date differs from lock")
        if not schema.get("reviewed"):
            raise ContractError("audit source schema before preparing official facts")
        facts, excluded, profile = normalize_padron(
            source_path(entry["source_id"]),
            schema,
            entry["reference_date"],
            entry["source_id"],
        )
        output = root / entry["output"]
        output.parent.mkdir(parents=True, exist_ok=True)
        if not facts:
            raise ContractError("no source facts")
        with output.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(facts[0]))
            writer.writeheader()
            writer.writerows(facts)
        pq.write_table(
            pa.Table.from_pylist(facts),
            output.with_suffix(".parquet"),
            compression="zstd",
        )
        output.with_suffix(".profile.json").write_text(json.dumps(profile, indent=2))
        output.with_suffix(".excluded.json").write_text(json.dumps(excluded, indent=2))
        outputs.append(str(output))
    for entry in project.get("source_ingestion", {}).get("mortality", []):
        selection = json.loads((root / entry["selection"]).read_text())
        values = extract_ine_series(
            json.loads(source_path(entry["source_id"]).read_text()), selection
        )
        output = root / entry["output"]
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["year", "age", "sex", "qx"])
            writer.writerows((*key, value) for key, value in sorted(values.items()))
        outputs.append(str(output))
    for entry in project.get("source_ingestion", {}).get("gis", []):
        source = source_path(entry["source_id"])
        # Immutable archive filenames are checksums. GDAL needs /vsizip/ explicitly.
        if entry.get("format") == "zip":
            import tempfile
            import shutil

            with tempfile.TemporaryDirectory() as temporary:
                archive = Path(temporary) / "source.zip"
                shutil.copyfile(source, archive)
                import_gis(
                    archive,
                    root / entry["output"],
                    entry["layer"],
                    entry["id_field"],
                    entry.get("prefix", "28079"),
                )
        else:
            import_gis(
                source,
                root / entry["output"],
                entry["layer"],
                entry["id_field"],
                entry.get("prefix", "28079"),
            )
        outputs.append(entry["output"])
    return outputs
