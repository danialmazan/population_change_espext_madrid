import csv
import json
import tempfile
import unittest
from pathlib import Path

from madrid_demography.profile import profile_population, profile_mortality


class ProfileTests(unittest.TestCase):
    def test_blanks_terminal_age_and_split_parent_are_reported_without_coercion(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.csv"
            path.write_text(
                "COD_DISTRITO;COD_DIST_BARRIO;COD_DIST_SECCION;COD_EDAD_INT;"
                "EspanolesHombres;EspanolesMujeres;ExtranjerosHombres;ExtranjerosMujeres\n"
                "19;1901;19036;45;1;;0;0\n"
                "19;1902;19036;45;6;5;1;2\n"
                "19;1902;19036;100 o +;0;1;0;0\n"
            )
            result = profile_population(path, "utf-8", ";")
            self.assertEqual(result["blank_count_cells"], {"ESPANOLESMUJERES": 1})
            self.assertEqual(result["open_age_labels"], {"100 o +": 1})
            self.assertEqual(result["invalid_ages"], 0)
            self.assertEqual(result["duplicate_section_age_rows"], 1)
            self.assertEqual(result["sections_with_multiple_barrios"], [19036])
            self.assertEqual(result["known_population_sum"], 16)
            self.assertEqual(result["status"], "requires_review")

    def test_mortality_checks_single_age_coverage_and_spanish_numeric_format(self):
        with tempfile.TemporaryDirectory() as directory:
            path, metadata = (
                Path(directory) / "data.csv",
                Path(directory) / "series.json",
            )
            metadata.write_text(
                json.dumps(
                    [
                        {
                            "Nombre": "Total Nacional. Hombres. 0 años. Riesgo de muerte. Dato base.",
                            "T3_Unidad": "Tanto por mil",
                        }
                    ]
                )
            )
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
            result = profile_mortality(path, metadata, region=None)
            self.assertTrue(result["covers_single_ages_0_99_2015_2024"])
            self.assertTrue(result["risk_values_in_0_1000"])
            self.assertEqual(result["single_age_cells_missing_0_99"], 0)

    def test_grouped_mortality_is_not_accepted_as_single_age(self):
        with tempfile.TemporaryDirectory() as directory:
            path, metadata = (
                Path(directory) / "data.csv",
                Path(directory) / "series.json",
            )
            metadata.write_text(
                json.dumps(
                    [
                        {
                            "Nombre": "Madrid, Comunidad de. Hombres. De 1 a 4 años. Riesgo de muerte. Dato base.",
                            "T3_Unidad": "Tanto por mil",
                        }
                    ]
                )
            )
            path.write_text(
                "Comunidades y Ciudades Autónomas;Sexo;Edad;Funciones;Periodo;Total\n"
                "13 Madrid, Comunidad de;Hombres;De 1 a 4 años;Riesgo de muerte;2024;0,100000\n"
            )
            result = profile_mortality(path, metadata, region="Madrid, Comunidad de")
            self.assertFalse(result["covers_single_ages_0_99_2015_2024"])
            self.assertEqual(result["single_age_cells_missing_0_99"], 2000)
