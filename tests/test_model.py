from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from madrid_demography.io import ContractError, Geography, read_population
from madrid_demography.model import build_analysis, survival_probability


class ModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.geographies = {
            "S1": Geography("S1", "Section", "section", "B1", "unchanged", "direct"),
            "B1": Geography("B1", "Barrio", "barrio", "MAD", "unchanged", "aggregate"),
            "MAD": Geography("MAD", "Madrid", "city", None, "unchanged", "aggregate"),
        }
        self.mortality = {
            (year, age, sex): 0.01
            for year in range(2015, 2025)
            for age in range(131)
            for sex in ("male", "female")
        }

    def test_survival_is_compounded_annually(self) -> None:
        result = survival_probability(25, "female", 2015, 2025, self.mortality)
        self.assertAlmostEqual(result, 0.99**10)

    def test_residual_and_hierarchy_are_additive(self) -> None:
        start = {
            ("S1", 25, "male", "ESP"): 100,
            ("S1", 25, "female", "EXT"): 50,
        }
        end = {
            ("S1", 35, "male", "ESP"): 105,
            ("S1", 35, "female", "EXT"): 45,
            ("S1", 5, "female", "ESP"): 12,
        }
        result = build_analysis(
            start, end, self.mortality, self.geographies, 2015, 2025
        )
        areas = {area["id"]: area for area in result["areas"]}
        expected = 150 * 0.99**10
        self.assertAlmostEqual(areas["S1"]["expected"], expected, places=3)
        self.assertAlmostEqual(areas["S1"]["residual"], 150 - expected, places=3)
        self.assertEqual(areas["S1"]["observed_under_interval"], 12)
        self.assertEqual(areas["S1"]["residual"], areas["MAD"]["residual"])

    def test_missing_mortality_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing mortality"):
            build_analysis(
                {("S1", 25, "male", "ESP"): 1},
                {},
                {},
                self.geographies,
                2015,
                2025,
            )

    def test_duplicate_input_cell_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "population.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    ["geography_id", "age", "sex", "nationality", "population"]
                )
                writer.writerow(["S1", 25, "male", "ESP", 1])
                writer.writerow(["S1", 25, "male", "ESP", 2])
            with self.assertRaisesRegex(ContractError, "duplicate"):
                read_population(path)


if __name__ == "__main__":
    unittest.main()
