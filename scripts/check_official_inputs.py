"""Verify pinned inputs and corroboration; never approve a model release."""

import csv
import hashlib
import json
from pathlib import Path
from madrid_demography.acquisition import read_lock, verify_sources
from madrid_demography.profile import COUNTS


def compare_exports(left, right, sources):
    def rows(sid):
        source = sources[sid]
        with (Path("data/raw") / sid / source["sha256"]).open(
            encoding=source["encoding"], newline=""
        ) as handle:
            for row in csv.DictReader(handle, delimiter=source["delimiter"]):
                yield tuple(
                    sorted((k.strip().upper(), v.strip()) for k, v in row.items())
                )

    from itertools import zip_longest

    count = 0
    for left_row, right_row in zip_longest(rows(left), rows(right)):
        if left_row != right_row:
            raise ValueError(f"CSV/TXT mismatch at data row {count + 1}")
        count += 1
    return count


def main():
    checks = verify_sources("sources.lock.yml", "data/raw")
    if not all(c["passed"] for c in checks):
        raise ValueError("Missing or changed source snapshots")
    sources = {s["id"]: s for s in read_lock("sources.lock.yml")["sources"]}
    count = compare_exports("padron_january_2015", "padron_january_2015_txt", sources)
    profiles = {
        p["source_id"]: p
        for p in json.loads(Path("docs/audit/padron_profiles.json").read_text())[
            "profiles"
        ]
    }
    controls = []
    bank_keys = dict(
        zip(COUNTS, ["NHombresNac", "NMujeresNac", "NHombresExt", "NMujeresExt"])
    )
    for year in (2015, 2025):
        path = Path(f"docs/audit/monthly-bank-{year}.json")
        response = json.loads(path.read_bytes().decode("iso-8859-1"))
        if response["status"] != "success" or response["mapaEpigrafesFiltros"][
            "Año: "
        ] != str(year):
            raise ValueError("Wrong monthly control reference")
        counts = response["listaConsulta"][0]
        profile = profiles[f"padron_january_{year}"]
        if profile["sha256"] != sources[f"padron_january_{year}"]["sha256"]:
            raise ValueError("Stale population profile")
        for column, key in bank_keys.items():
            if counts[key] != profile["known_population_by_column"][column]:
                raise ValueError("Monthly independent count differs")
        controls.append(
            dict(
                year=year,
                known_total=sum(counts[k] for k in bank_keys.values()),
                all_four_cells_match=True,
                response_encoding="iso-8859-1",
                response_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    report = dict(
        production_ready=False,
        manifest_sha256=hashlib.sha256(
            Path("sources.lock.yml").read_bytes()
        ).hexdigest(),
        verified_snapshots=len(checks),
        alternate_2015_export_rows_identical=count,
        monthly_controls=controls,
        blank_count_policy="unknown_null",
        release_blockers=[
            "Blank-cell interpretation requires explicit source policy/review",
            "Monthly versus revised annual series differences require review",
            "Boundary changes and historical parents require review",
            "Independent survival, sensitivity and licensing reviews pending",
        ],
    )
    Path("docs/audit/integration.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
