import unittest
from shapely.geometry import box
from madrid_demography.parent_geometry import (
    canonical_parent,
    require_parent_vintage,
    containment_review,
)
from madrid_demography.io import ContractError


class ParentGeometryTests(unittest.TestCase):
    def test_parent_codes_follow_reviewed_three_digit_convention(self):
        self.assertEqual(canonical_parent("1", "011"), "0101")
        self.assertEqual(canonical_parent("18", "183"), "1803")
        self.assertEqual(canonical_parent("1"), "01")
        for district, barrio in [("1", "021"), ("18", "180"), ("22", None)]:
            with self.assertRaises(ContractError):
                canonical_parent(district, barrio)

    def test_layer_filename_and_publication_year_do_not_establish_endpoint_validity(
        self,
    ):
        candidate = dict(
            temporal_validity_verified=False,
            layer="20250101_barrio.shp",
            valid_from="2021-07-12",
            valid_to="2025-10-21",
            validity_evidence="reviewed-source",
        )
        with self.assertRaises(ContractError):
            require_parent_vintage(candidate, "2025-01-01")
        candidate["temporal_validity_verified"] = True
        require_parent_vintage(candidate, "2025-01-01")
        with self.assertRaises(ContractError):
            require_parent_vintage(candidate, "2015-01-01")
        candidate["valid_from"] = "2025-10-22"
        with self.assertRaises(ContractError):
            require_parent_vintage(candidate, "2025-01-01")
        candidate["valid_from"] = "bad-date"
        with self.assertRaises(ContractError):
            require_parent_vintage(candidate, "2025-01-01")

    def test_partial_intersection_is_not_parent_containment(self):
        result = containment_review(
            {"S": box(0, 0, 10, 10)},
            {"0101": box(0, 0, 9, 10)},
            {"S": {("01", "0101")}},
            {"S": 100},
            "barrio",
        )
        self.assertEqual(result[0]["status"], "outside_declared_parent")
        self.assertAlmostEqual(result[0]["outside_area_ratio"], 0.1)
        self.assertEqual(result[0]["known_population"], 100)

    def test_ambiguous_membership_is_preserved_and_missing_parent_not_guessed(self):
        sections = {"S": box(0, 0, 10, 10)}
        parents = {"0101": box(0, 0, 5, 10), "0102": box(5, 0, 10, 10)}
        membership = {"S": {("01", "0101"), ("01", "0102")}}
        result = containment_review(sections, parents, membership, {"S": 10}, "barrio")
        self.assertEqual(result[0]["status"], "contained_candidate")
        self.assertTrue(result[0]["ambiguous_raw_parent"])
        result = containment_review(sections, {}, membership, {"S": 10}, "barrio")
        self.assertEqual(result[0]["status"], "missing_parent")
