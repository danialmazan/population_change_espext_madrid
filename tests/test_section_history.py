import unittest
from madrid_demography.section_history import (
    registry_date,
    parent_at_endpoint,
    compare_registry,
)
from madrid_demography.io import ContractError


class SectionHistoryTests(unittest.TestCase):
    def test_invalid_official_date_is_preserved_without_month_day_repair(self):
        parsed = registry_date(20171606.0)
        self.assertEqual(parsed["raw"], "20171606")
        self.assertEqual(parsed["status"], "invalid_date_year_only")
        self.assertIsNone(parsed["iso"])
        self.assertEqual(
            parent_at_endpoint("1803", "1801", parsed, "2015-01-01"),
            ("1801", "year_bracket_only"),
        )
        self.assertEqual(
            parent_at_endpoint("1803", "1801", parsed, "2025-01-01"),
            ("1803", "year_bracket_only"),
        )
        self.assertIsNone(parent_at_endpoint("1803", "1801", parsed, "2017-01-01")[0])
        with self.assertRaises(ContractError):
            registry_date(20171606.5)

    def test_dated_change_uses_prior_code_before_effective_date(self):
        parsed = registry_date(20171101)
        self.assertEqual(
            parent_at_endpoint("1902", "1901", parsed, "2015-01-01")[0], "1901"
        )
        self.assertEqual(
            parent_at_endpoint("1902", "1901", parsed, "2017-11-01")[0], "1902"
        )
        self.assertIsNone(
            parent_at_endpoint("1902", "1901", registry_date(""), "2015-01-01")[0]
        )

    def test_registry_retains_raw_split_membership_as_a_difference(self):
        record = dict(
            row_number=1,
            section_id="S",
            parent="1902",
            previous_parent="1901",
            created=registry_date(20000101),
            closed=registry_date(""),
            modified=registry_date(20171101),
        )
        result = compare_registry(
            [record], {"S": {("19", "1901"), ("19", "1902")}}, "2025-01-01"
        )
        self.assertEqual(result["matching_raw_section_memberships"], 0)
        self.assertEqual(result["differences"][0]["registry_parents"], ["1902"])
        self.assertEqual(result["differences"][0]["raw_parents"], ["1901", "1902"])
        record["closed"] = registry_date(20250101)
        result = compare_registry([record], {}, "2025-01-01")
        self.assertEqual(result["active_registry_sections"], 0)
