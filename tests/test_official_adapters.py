import unittest
from madrid_demography.normalize import canonical_barrio, normalize_padron
from madrid_demography.io import ContractError
import tempfile
from pathlib import Path


class OfficialAdapterTests(unittest.TestCase):
    def test_source_specific_barrio_format(self):
        self.assertEqual(canonical_barrio("1", "101", "district_times_100"), "0101")
        self.assertEqual(canonical_barrio("10", "1002", "district_times_100"), "1002")
        with self.assertRaises(ContractError):
            canonical_barrio("1", "201", "district_times_100")
        with self.assertRaises(ContractError):
            canonical_barrio("1", "101")

    def test_explicit_open_age_label_and_unknown_count_rejection(self):
        columns = [
            "district",
            "barrio",
            "section",
            "age",
            "male_ESP",
            "female_ESP",
            "male_EXT",
            "female_EXT",
        ]
        schema = dict(
            valid_from="2025-01-01",
            valid_to="2025-01-01",
            encoding="utf-8",
            delimiter=";",
            aliases={c: c for c in columns},
            schema_version="official-test",
            open_age=100,
            open_age_labels=["100 o +"],
            barrio_code_format="district_times_100",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.csv"
            path.write_text(";".join(columns) + "\n1;101;1;100 o +;1;2;3;4\n")
            facts, _, profile = normalize_padron(path, schema, "2025-01-01", "source")
            self.assertEqual(profile["total"], 10)
            self.assertTrue(
                all(f["age_kind"] == "open" and f["age"] == 100 for f in facts)
            )
            path.write_text(";".join(columns) + "\n1;101;1;100 o +;;2;3;4\n")
            with self.assertRaisesRegex(ContractError, "invalid/suppressed count"):
                normalize_padron(path, schema, "2025-01-01", "source")
