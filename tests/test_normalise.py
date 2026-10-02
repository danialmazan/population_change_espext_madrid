import csv
import tempfile
import unittest
import zipfile
from pathlib import Path

from madrid_demography.normalise import (
    age_fields,
    normalise_population,
    normalise_mortality,
)
from madrid_demography.profile import profile_population
from madrid_demography.reconcile import comparisons, published_totals, municipal_totals


CONFIG = {
    "start_date": "2015-01-01",
    "end_date": "2025-01-01",
    "cohort_endpoint_age_min": 10,
    "cohort_endpoint_age_max": 99,
    "mortality_measure": "Riesgo de muerte",
    "mortality_unit_divisor": 1000,
    "mortality_region": "Spain",
}


class NormaliseTests(unittest.TestCase):
    def test_published_no_consta_category_closes_the_nationality_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "publication.zip"
            cells = {
                "C": 100,
                "D": 50,
                "E": 50,
                "G": 60,
                "H": 30,
                "I": 30,
                "K": 35,
                "L": 18,
                "M": 17,
                "O": 5,
                "P": 2,
                "Q": 3,
            }
            values = "".join(
                f'<c r="{column}8"><v>{value}</v></c>'
                for column, value in cells.items()
            )
            sheet = (
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                '<row r="2"><c r="A2" t="inlineStr"><is><t>revisado a 1 de enero de 2015</t></is></c></row>'
                '<row r="5"><c r="O5" t="inlineStr"><is><t>No consta</t></is></c></row>'
                '<row r="8"><c r="A8" t="inlineStr"><is><t>Ciudad de Madrid</t></is></c>'
                + values
                + "</row></sheetData></worksheet>"
            )
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(
                    "xl/workbook.xml",
                    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="2015" r:id="rId1"/></sheets></workbook>',
                )
                archive.writestr(
                    "xl/_rels/workbook.xml.rels",
                    '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
                )
                archive.writestr("xl/worksheets/sheet1.xml", sheet)
            result = municipal_totals(path, 2015)
            self.assertEqual(result["nationality_groups_gap"], 5)
            self.assertEqual(result["city_counts"]["no_consta_total"], 5)
            self.assertEqual(result["city_row"], 8)

    def test_terminal_exclusion_is_paired_and_births_are_observed_only(self):
        self.assertEqual(age_fields("89", 2015, CONFIG)[2], "eligible")
        self.assertEqual(age_fields("90", 2015, CONFIG)[2], "excluded_terminal")
        self.assertEqual(age_fields("99", 2025, CONFIG)[2], "eligible")
        self.assertEqual(
            age_fields("100 o +", 2025, CONFIG)[:2], (None, "open_100_plus")
        )
        self.assertEqual(
            age_fields("9", 2025, CONFIG)[2], "observed_born_during_interval"
        )
        self.assertEqual(age_fields("135", 2015, CONFIG)[2], "excluded_invalid_age")

    def test_missing_geometry_blank_counts_and_split_parents_are_conserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path, output = Path(directory) / "raw.csv", Path(directory) / "long.csv"
            header = "COD_DISTRITO;COD_DIST_BARRIO;COD_DIST_SECCION;COD_EDAD_INT;EspanolesHombres;EspanolesMujeres;ExtranjerosHombres;ExtranjerosMujeres"
            path.write_text(
                header
                + "\n19;1901;19036;45;1;;0;0\n19;1902;19036;45;6;5;1;2\n6;606;;42;0;0;1;0\n"
            )
            contract = {
                "encoding": "utf-8",
                "delimiter": ";",
                "schema_version": 1,
                "columns": {h: h.upper() for h in header.split(";")},
            }
            source = {"id": "test", "sha256": "test", "reference_date": "2025-01-01"}
            report = normalise_population(
                path, source, contract, CONFIG, output, {"2807919036"}
            )
            with output.open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(report["known_population_sum"], 16)
            self.assertEqual(report["unknown_count_cells"], 1)
            self.assertEqual(report["known_population_without_geometry"], 1)
            self.assertEqual(
                report["sections_with_multiple_barrios"], {"2807919036": [1901, 1902]}
            )
            self.assertEqual(
                next(r for r in rows if r["population_status"] == "unknown_blank")[
                    "population"
                ],
                "",
            )
            self.assertEqual(
                sum(
                    int(r["population"] or 0)
                    for r in rows
                    if not r["source_geography_id"]
                ),
                1,
            )
            profile = profile_population(path, "utf-8", ";")
            self.assertEqual(
                profile["known_population_sum"], report["known_population_sum"]
            )
            self.assertEqual(profile["invalid_geography_known_population"], 1)

    def test_mortality_conversion_and_terminal_group_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path, output = Path(directory) / "raw.csv", Path(directory) / "qx.csv"
            with path.open("w", newline="") as handle:
                writer = csv.writer(handle, delimiter=";")
                writer.writerow(["Sexo", "Edad", "Funciones", "Periodo", "Total"])
                for year in range(2015, 2025):
                    for sex in ("Hombres", "Mujeres"):
                        for age in range(100):
                            writer.writerow(
                                [
                                    sex,
                                    "1 año" if age == 1 else f"{age} años",
                                    "Riesgo de muerte",
                                    year,
                                    "1,000000",
                                ]
                            )
                        writer.writerow(
                            [
                                sex,
                                "100 y más años",
                                "Riesgo de muerte",
                                year,
                                "1.000,000000",
                            ]
                        )
            report = normalise_mortality(path, output, CONFIG)
            self.assertEqual(report["cells"], 2000)
            with output.open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertTrue(all(float(r["qx"]) == 0.001 for r in rows))
            self.assertTrue(all(int(r["age"]) < 100 for r in rows))

    def test_inconsistent_published_sex_totals_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ine.csv"
            path.write_text(
                "Municipios;Sexo;Periodo;Total\n28079 Madrid;Total;2015;100\n"
                "28079 Madrid;Hombres;2015;60\n28079 Madrid;Mujeres;2015;50\n"
            )
            with self.assertRaisesRegex(ValueError, "sex totals"):
                published_totals(path, {2015})

    def test_mismatched_totals_remain_unresolved_without_adjustments(self):
        profile = {
            "reference_date": "2015-01-01",
            "source_id": "test",
            "sha256": "test",
            "known_population_by_column": {
                "ESPANOLESHOMBRES": 40,
                "EXTRANJEROSHOMBRES": 10,
                "ESPANOLESMUJERES": 35,
                "EXTRANJEROSMUJERES": 15,
            },
            "known_population_sum": 100,
            "blank_count_cells": {"ESPANOLESHOMBRES": 1},
        }
        result = comparisons(
            [profile], {2015: {"Total": 95, "Hombres": 45, "Mujeres": 50}}
        )[0]
        self.assertEqual(result["differences"]["Total"], 5)
        self.assertEqual(result["status"], "different_series_unresolved")
        self.assertFalse(result["counts_adjusted"])
