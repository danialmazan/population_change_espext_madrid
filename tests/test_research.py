"""Research controls must fail closed before missing cells become analytical zeros."""

import csv
import math
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from madrid_demography.io import ContractError
from madrid_demography.profile import COUNTS
from madrid_demography.research import (
    calibrate_band,
    independent_expected,
    read_research_population,
)


class ResearchChecks(unittest.TestCase):
    def fixture(self, root):
        path = Path(root) / "raw.csv"
        fields = [
            "COD_DISTRITO",
            "COD_DIST_BARRIO",
            "COD_DIST_SECCION",
            "COD_EDAD_INT",
            *COUNTS,
        ]
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, delimiter=";")
            writer.writeheader()
            writer.writerow(
                dict(zip(fields, ["1", "101", "1001", "55", "10", "", "3", ""]))
            )
        return path, {
            "id": "test",
            "reference_date": "2015-01-01",
            "encoding": "utf-8",
            "delimiter": ";",
            "sha256": "test",
        }

    def controls(self, mismatch=False):
        ages = {(a, c): 0 for a in range(100) for c in COUNTS}
        ages[(55, COUNTS[0])] = 10 + int(mismatch)
        ages[(55, COUNTS[2])] = 3
        full = {
            ("total", c): sum(v for (a, column), v in ages.items() if column == c)
            for c in COUNTS
        }
        return lambda year, kind: (
            ages if kind == "ages" else full,
            "test-control-hash",
        )

    def test_matching_controls_allow_conditional_zero_and_preserve_raw_blanks(self):
        with tempfile.TemporaryDirectory() as root:
            path, source = self.fixture(root)
            original = path.read_bytes()
            with (
                patch("madrid_demography.research.pinned_path", return_value=path),
                patch(
                    "madrid_demography.research.monthly_control",
                    side_effect=self.controls(),
                ),
            ):
                city, spatial, _, report = read_research_population(
                    source, {"2807901001": "ZONE"}
                )
            self.assertEqual(sum(city.values()), 13)
            self.assertEqual(sum(spatial.values()), 13)
            self.assertEqual(report["conditionally_inferred_blank_cells"], 2)
            self.assertTrue(report["monthly_controls_matched"])
            self.assertEqual(path.read_bytes(), original)

    def test_control_discrepancy_blocks_inference_and_diagnostic_mode_keeps_unknowns(
        self,
    ):
        with tempfile.TemporaryDirectory() as root:
            path, source = self.fixture(root)
            with (
                patch("madrid_demography.research.pinned_path", return_value=path),
                patch(
                    "madrid_demography.research.monthly_control",
                    side_effect=self.controls(True),
                ),
            ):
                with self.assertRaisesRegex(ContractError, "control discrepancy"):
                    read_research_population(source)
                _, _, _, report = read_research_population(
                    source, require_matching_controls=False
                )
            self.assertFalse(report["monthly_controls_matched"])
            self.assertEqual(report["conditionally_inferred_blank_cells"], 0)
            self.assertEqual(report["raw_blank_cells"], 2)
            self.assertIn("unknown_null", report["policy"])

    def test_unmapped_population_is_separate_from_city_stock(self):
        with tempfile.TemporaryDirectory() as root:
            path, source = self.fixture(root)
            with (
                patch("madrid_demography.research.pinned_path", return_value=path),
                patch(
                    "madrid_demography.research.monthly_control",
                    side_effect=self.controls(),
                ),
            ):
                city, spatial, _, report = read_research_population(source, {})
            self.assertEqual(sum(city.values()), 13)
            self.assertFalse(spatial)
            self.assertEqual(report["unmapped_known_population"], 13)

    def test_band_calibration_preserves_regional_group_survival(self):
        national = [0.01, 0.02, 0.03, 0.04, 0.05]
        calibrated = calibrate_band(national, 0.2)
        self.assertAlmostEqual(math.prod(1 - q for q in calibrated), 0.8, places=14)
        self.assertEqual(sorted(calibrated), calibrated)
        with self.assertRaises(ContractError):
            calibrate_band([0, 0], 0.2)
        with self.assertRaises(ContractError):
            calibrate_band(national, 1)

    def test_independent_lx_propagation_ages_annually_and_excludes_terminal(self):
        start = {("CITY", 10, "male", "ESP"): 100, ("CITY", 99, "male", "ESP"): 100}
        lives = {
            (2015, 10, "male"): Decimal(100),
            (2015, 11, "male"): Decimal(90),
            (2016, 11, "male"): Decimal(80),
            (2016, 12, "male"): Decimal(40),
        }
        result = independent_expected(start, lives, 2015, 2017, 100)
        self.assertEqual(result, {("CITY", 12, "male", "ESP"): 45.0})
