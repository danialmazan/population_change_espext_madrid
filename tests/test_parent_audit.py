import csv
from pathlib import Path
import tempfile
import unittest
from madrid_demography.parent_audit import assess_parents, read_membership
from madrid_demography.io import ContractError


class ParentAuditTests(unittest.TestCase):
    def test_same_section_id_does_not_approve_changed_barrio(self):
        result = assess_parents(
            ["S"], ["S"], {"S": {("18", "1801")}}, {"S": {("18", "1803")}}
        )
        self.assertEqual(result["raw_parent_status"], "raw_parent_reassignment")
        self.assertTrue(result["stable_raw_district_code"])
        self.assertFalse(result["stable_raw_parent_code"])
        self.assertFalse(result["independent_historical_parent_boundaries_verified"])

    def test_multi_parent_zone_is_not_assigned_by_majority_or_current_code(self):
        membership = {"A": {("16", "1606")}, "B": {("21", "2102")}}
        result = assess_parents(["A", "B"], ["A", "B"], membership, membership)
        self.assertEqual(result["raw_parent_status"], "multi_parent_zone")
        self.assertFalse(result["stable_raw_district_code"])

    def test_split_membership_and_missing_membership_fail_closed(self):
        result = assess_parents(
            ["A"],
            ["A"],
            {"A": {("19", "1901")}},
            {"A": {("19", "1901"), ("19", "1902")}},
        )
        self.assertEqual(result["raw_parent_status"], "ambiguous_section_membership")
        self.assertEqual(result["ambiguous_new_sections"], ["A"])
        self.assertFalse(result["stable_raw_parent_code"])
        result = assess_parents(["A"], ["A"], {"A": {("19", "1901")}}, {})
        self.assertEqual(result["raw_parent_status"], "missing_raw_membership")
        self.assertFalse(result["stable_raw_district_code"])

    def test_stable_code_is_not_independent_boundary_verification(self):
        membership = {"A": {("1", "0101")}}
        result = assess_parents(["A"], ["A"], membership, membership)
        self.assertTrue(result["stable_raw_parent_code"])
        self.assertFalse(result["independent_historical_parent_boundaries_verified"])
        missing = {"A": {("01", "0000")}}
        self.assertEqual(
            assess_parents(["A"], ["A"], missing, missing)["raw_parent_status"],
            "unknown_raw_barrio",
        )

    def test_zero_blank_and_exception_rows_preserve_membership_and_counts(self):
        fields = [
            "COD_DISTRITO",
            "COD_DIST_BARRIO",
            "COD_DIST_SECCION",
            "ESPANOLESHOMBRES",
            "ESPANOLESMUJERES",
            "EXTRANJEROSHOMBRES",
            "EXTRANJEROSMUJERES",
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.csv"
            with path.open("w", newline="") as handle:
                writer = csv.writer(handle, delimiter=";")
                writer.writerow(fields)
                writer.writerows(
                    [
                        [19, 1901, 19036, 0, "", 0, 0],
                        [19, 1902, 19036, 4, 5, 6, 7],
                        [6, 606, "", 1, 0, 0, 0],
                        [1, 0, 1888, 1, 0, 0, 0],
                    ]
                )
            source = dict(encoding="utf-8", delimiter=";")
            parents, counts, _, missing = read_membership(path, source)
            self.assertEqual(parents["2807919036"], {("19", "1901"), ("19", "1902")})
            self.assertEqual(counts["2807919036"], 22)
            self.assertEqual(sum(counts.values()) + missing, 24)
            with path.open("a") as handle:
                handle.write("1;201;1001;1;0;0;0\n")
            with self.assertRaises(ContractError):
                read_membership(path, source)
