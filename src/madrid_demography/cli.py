from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
from .acquisition import acquire, read_lock, discover_catalogue
from .normalize import (
    normalize_padron,
    discontinuities,
    extract_mortality,
    extract_ine_series,
)
from .pipeline import run_project
from .io import ContractError


def parser():
    result = argparse.ArgumentParser(
        description="Auditable Madrid demographic residual pipeline"
    )
    sub = result.add_subparsers(dest="command", required=True)
    acq = sub.add_parser(
        "acquire",
        help="download exact manifest resources without automatically approving them",
    )
    acq.add_argument("--lock", default="sources.lock.yml")
    acq.add_argument("--root", default="data/raw")
    acq.add_argument("--id")
    discovery = sub.add_parser("discover")
    discovery.add_argument("catalogue")
    normal = sub.add_parser("normalize")
    normal.add_argument("input")
    normal.add_argument("--schemas", default="config/schema-aliases.json")
    normal.add_argument("--schema", required=True)
    normal.add_argument("--date", required=True)
    normal.add_argument("--source-id", required=True)
    normal.add_argument("--output", required=True)
    series = sub.add_parser("diagnose")
    series.add_argument("profiles", nargs="+")
    series.add_argument("--output", required=True)
    mortality = sub.add_parser("mortality")
    mortality.add_argument("input")
    mortality.add_argument("--measure", choices=["qx", "px", "lx"], required=True)
    mortality.add_argument("--units", required=True)
    mortality.add_argument("--output", required=True)
    gis = sub.add_parser("import-gis")
    gis.add_argument("input")
    gis.add_argument("--layer", required=True)
    gis.add_argument("--id-field", required=True)
    gis.add_argument("--prefix", default="28079")
    gis.add_argument("--output", required=True)
    ine = sub.add_parser("ine")
    ine.add_argument("input")
    ine.add_argument("--selection", required=True)
    ine.add_argument("--output", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("project")
    audit = sub.add_parser("overlay")
    audit.add_argument("--old", required=True)
    audit.add_argument("--new", required=True)
    audit.add_argument("--crs", required=True)
    audit.add_argument("--output", required=True)
    audit.add_argument("--reviews")
    build = sub.add_parser("build")
    build.add_argument("project")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command == "acquire":
        for source in read_lock(args.lock)["sources"]:
            if args.id and source["id"] != args.id:
                continue
            try:
                print(json.dumps(acquire(source, args.root)))
            except Exception as exc:
                # Keep source-specific failures visible; preserve successful immutable acquisitions.
                print(json.dumps({"id": source["id"], "error": str(exc)}))
                raise
    elif args.command == "discover":
        print(json.dumps(discover_catalogue(args.catalogue), indent=2))
    elif args.command == "normalize":
        schemas = json.loads(Path(args.schemas).read_text())["schemas"]
        matched = [s for s in schemas if s["schema_version"] == args.schema]
        if len(matched) != 1:
            raise ContractError("schema ID must select exactly one version")
        facts, excluded, profile = normalize_padron(
            args.input, matched[0], args.date, args.source_id
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        if not facts:
            raise ContractError("no exact-age facts")
        with output.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(facts[0]))
            writer.writeheader()
            writer.writerows(facts)
        import pyarrow as pa
        import pyarrow.parquet as pq

        pq.write_table(
            pa.Table.from_pylist(facts),
            output.with_suffix(".parquet"),
            compression="zstd",
            use_dictionary=True,
        )
        output.with_suffix(".profile.json").write_text(json.dumps(profile, indent=2))
        output.with_suffix(".excluded.json").write_text(json.dumps(excluded, indent=2))
    elif args.command == "diagnose":
        profiles = [json.loads(Path(p).read_text()) for p in args.profiles]
        Path(args.output).write_text(json.dumps(discontinuities(profiles), indent=2))
    elif args.command == "mortality":
        with Path(args.input).open() as f:
            values = extract_mortality(
                list(csv.DictReader(f)), args.measure, args.units
            )
        with Path(args.output).open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["year", "age", "sex", "qx"])
            writer.writerows((*key, value) for key, value in sorted(values.items()))
    elif args.command == "import-gis":
        from .geography import import_gis

        print(
            json.dumps(
                import_gis(
                    args.input, args.output, args.layer, args.id_field, args.prefix
                )
            )
        )
    elif args.command == "ine":
        values = extract_ine_series(
            json.loads(Path(args.input).read_text()),
            json.loads(Path(args.selection).read_text()),
        )
        with Path(args.output).open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["year", "age", "sex", "qx"])
            writer.writerows((*key, value) for key, value in sorted(values.items()))
    elif args.command == "prepare":
        from .prepare import prepare_project

        print(json.dumps(prepare_project(args.project), indent=2))
    elif args.command == "overlay":
        from .geography import read_geometry, overlay, feature_collection

        report = overlay(
            read_geometry(args.old, args.crs),
            read_geometry(args.new, args.crs),
            reviews=json.loads(Path(args.reviews).read_text()) if args.reviews else {},
        )
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        (output / "zones.geojson").write_text(
            json.dumps(feature_collection(report.pop("zones")))
        )
        (output / "boundary-audit.json").write_text(json.dumps(report, indent=2))
    elif args.command == "build":
        manifest = run_project(args.project)
        print(
            f"Built {manifest['config']['start_date']} → {manifest['config']['end_date']} ({manifest['dataset_kind']})"
        )


if __name__ == "__main__":
    main()
