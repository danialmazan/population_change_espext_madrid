"""Exercise the real project orchestrator through a temporary normalized fixture."""

import csv
import json
from pathlib import Path
import tempfile
import unittest
from shapely.geometry import box
from madrid_demography.geography import feature_collection
from madrid_demography.pipeline import run_project


class ProjectTests(unittest.TestCase):
    def test_config_driven_build_exports_audits_crosswalk_and_exact_tier(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def write_csv(name, header, rows):
                with (root / name).open("w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(header)
                    writer.writerows(rows)

            write_csv(
                "start.csv",
                ["geography_id", "age", "sex", "nationality", "population"],
                [["S", 25, "female", "ESP", 100]],
            )
            write_csv(
                "end.csv",
                ["geography_id", "age", "sex", "nationality", "population"],
                [["S", 35, "female", "ESP", 105], ["S", 5, "female", "ESP", 8]],
            )
            write_csv(
                "mortality.csv",
                ["year", "age", "sex", "qx"],
                [
                    [y, a, s, 0.001]
                    for y in range(2015, 2025)
                    for a in range(131)
                    for s in ["male", "female"]
                ],
            )
            write_csv(
                "geographies.csv",
                [
                    "area_id",
                    "name",
                    "level",
                    "parent_id",
                    "boundary_status",
                    "boundary_method",
                ],
                [
                    ["S", "Section", "section", "B", "unchanged", "unchanged"],
                    ["B", "Barrio", "barrio", "D", "unchanged", "aggregate"],
                    ["D", "District", "district", "MAD", "unchanged", "aggregate"],
                    ["MAD", "Madrid", "city", "", "unchanged", "aggregate"],
                ],
            )
            for name, gid in [
                ("sections", "S"),
                ("barrios", "B"),
                ("districts", "D"),
                ("municipality", "MAD"),
            ]:
                (root / (name + ".geojson")).write_text(
                    json.dumps(
                        feature_collection({gid: box(440000, 4470000, 441000, 4471000)})
                    )
                )
            project = {
                "model": {
                    "start_date": "2015-01-01",
                    "end_date": "2025-01-01",
                    "dataset_kind": "demonstration",
                },
                "start": "start.csv",
                "end": "end.csv",
                "mortality": "mortality.csv",
                "geographies": "geographies.csv",
                "output": "output",
                "geometry_audit": {
                    "old": "sections.geojson",
                    "new": "sections.geojson",
                    "crs": "EPSG:25830",
                    "municipality": "municipality.geojson",
                    "parents": {
                        "barrio": {
                            "old": "barrios.geojson",
                            "new": "barrios.geojson",
                            "crs": "EPSG:25830",
                        },
                        "district": {
                            "old": "districts.geojson",
                            "new": "districts.geojson",
                            "crs": "EPSG:25830",
                        },
                    },
                },
                "web_geometry": {
                    level: {"path": name + ".geojson", "crs": "EPSG:25830"}
                    for level, name in [
                        ("barrio", "barrios"),
                        ("district", "districts"),
                        ("city", "municipality"),
                    ]
                },
            }
            config = root / "project.json"
            config.write_text(json.dumps(project))
            result = run_project(config)
            self.assertEqual(result["dataset_kind"], "demonstration")
            self.assertTrue((root / "output" / "exact" / "manifest.json").exists())
            self.assertTrue(
                (root / "data" / "intermediate" / "common_zones.parquet").exists()
            )
            report = json.loads(
                (root / "output" / "reports" / "feasibility.json").read_text()
            )
            self.assertTrue(report["section_gate_passed"])
            self.assertTrue(
                (root / "output" / "downloads" / "cohort_detail.parquet").exists()
            )
