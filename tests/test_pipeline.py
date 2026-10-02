from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from shapely.geometry import box
from madrid_demography.config import ModelConfig
from madrid_demography.io import ContractError, Geography
from madrid_demography.geography import (
    overlay,
    harmonize,
    assign_parents,
    topology_audit,
    capacity_weights,
    validate_crosswalk,
)
from madrid_demography.normalize import (
    normalize_padron,
    extract_mortality,
    discontinuities,
)
from madrid_demography.model import build_analysis
from madrid_demography.qa import validate_analysis, official_release_gate, reconcile
from madrid_demography.scenarios import births_counterfactual, nationality_scenarios
from madrid_demography.export import write_bundle


class GeographyTests(unittest.TestCase):
    def test_split_and_merge_preserve_population_in_exact_union(self):
        audit = overlay(
            {"old": box(0, 0, 2, 1)},
            {"left": box(0, 0, 1, 1), "right": box(1, 0, 2, 1)},
            reviews={"unused": "test"},
        )
        self.assertEqual(audit["components"][0]["classification"], "split")
        self.assertEqual(
            audit["components"][0]["quality_status"], "exact_harmonisation"
        )
        zid = audit["components"][0]["zone_id"]
        start = harmonize(
            {("old", 30, "male", "ESP"): 100},
            [r for r in audit["crosswalk"] if r["vintage"] == "old"],
        )
        end = harmonize(
            {("left", 40, "male", "ESP"): 40, ("right", 40, "male", "ESP"): 60},
            [r for r in audit["crosswalk"] if r["vintage"] == "new"],
        )
        self.assertEqual(start[(zid, 30, "male", "ESP")], end[(zid, 40, "male", "ESP")])
        self.assertTrue(audit["components"][0]["requires_review"])

    def test_equal_id_does_not_imply_equal_boundary(self):
        audit = overlay({"same": box(0, 0, 1, 1)}, {"same": box(0.2, 0, 1.2, 1)})
        self.assertEqual(audit["components"][0]["quality_status"], "unreliable")

    def test_changed_parent_is_not_inferred_from_current_membership(self):
        with self.assertRaises(ContractError):
            assign_parents(
                {"z": box(0, 0, 1, 1)}, {"b": box(0, 0, 2, 2)}, {"b": box(0, 0, 3, 2)}
            )

    def test_source_overlaps_are_reported(self):
        self.assertFalse(
            topology_audit({"a": box(0, 0, 1, 1), "b": box(0.5, 0, 1.5, 1)})["valid"]
        )

    def test_crosswalk_rejects_mass_loss_and_fractional_exact_claims(self):
        row = {
            "source_id": "s",
            "zone_id": "z",
            "weight": 0.5,
            "quality_status": "exact_harmonisation",
        }
        with self.assertRaises(ContractError):
            validate_crosswalk([row], {"s"})
        row["quality_status"] = "unreliable"
        with self.assertRaises(ContractError):
            validate_crosswalk([row], {"s"})

    def test_capacity_weights_require_temporal_evidence_and_show_sensitivity(self):
        buildings = [
            {
                "geometry": box(0, 0, 1, 1),
                "capacity": 10,
                "vintage": 2015,
                "license": "CC0",
            },
            {
                "geometry": box(1, 0, 2, 1),
                "capacity": 30,
                "vintage": 2015,
                "license": "CC0",
            },
        ]
        weights, sensitivity = capacity_weights(
            box(0, 0, 2, 1),
            {"a": box(0, 0, 1, 1), "b": box(1, 0, 2, 1)},
            buildings,
            2015,
            "reviewer",
        )
        self.assertEqual(weights, {"a": 0.25, "b": 0.75})
        self.assertEqual(sensitivity["a"], -0.25)
        with self.assertRaises(ContractError):
            capacity_weights(
                box(0, 0, 2, 1), {"a": box(0, 0, 2, 1)}, buildings, 2025, "reviewer"
            )


class AnalyticalTests(unittest.TestCase):
    def setUp(self):
        self.geo = {
            "s": Geography("s", "Section", "section", "MAD", "unchanged", "unchanged"),
            "MAD": Geography("MAD", "Madrid", "city", None, "unchanged", "aggregate"),
        }
        self.mortality = {
            (y, a, s): 0.1
            for y in range(2015, 2025)
            for a in range(131)
            for s in ["male", "female"]
        }
        self.start = {("s", 25, "female", "ESP"): 100, ("s", 25, "male", "EXT"): 50}
        self.end = {
            ("s", 35, "female", "ESP"): 120,
            ("s", 35, "male", "EXT"): 30,
            ("s", 5, "female", "ESP"): 8,
        }

    def test_nationality_switch_cancels_in_combined_residual(self):
        first = build_analysis(
            self.start, self.end, self.mortality, self.geo, 2015, 2025
        )
        shifted = dict(self.end)
        shifted[("s", 35, "female", "ESP")] -= 20
        shifted[("s", 35, "male", "EXT")] += 20
        second = build_analysis(
            self.start, shifted, self.mortality, self.geo, 2015, 2025
        )
        self.assertEqual(first["areas"][0]["residual"], second["areas"][0]["residual"])
        self.assertTrue(validate_analysis(first, self.geo)["passed"])

    def test_terminal_and_birth_cells_never_receive_residuals(self):
        start = {("s", 99, "female", "ESP"): 10}
        end = {("s", 109, "female", "ESP"): 2, ("s", 3, "female", "ESP"): 4}
        result = build_analysis(start, end, {}, self.geo, 2015, 2025, terminal_age=100)
        rows = result["areas"][0]["profile"]
        self.assertTrue(all(r["residual"] is None for r in rows))
        self.assertEqual(sum(r["actual"] for r in rows), 6)

    def test_tiny_expected_denominator_suppresses_rate_not_counts(self):
        result = build_analysis(
            {("s", 25, "male", "ESP"): 1},
            {("s", 35, "male", "ESP"): 2},
            self.mortality,
            self.geo,
            2015,
            2025,
            min_expected=20,
        )
        self.assertIsNone(result["areas"][0]["residual_per_1000"])
        self.assertGreater(result["areas"][0]["residual"], 0)

    def test_aggregate_quality_carries_unreliable_descendants(self):
        geo = dict(self.geo)
        geo["s"] = replace(geo["s"], boundary_status="unreliable")
        result = build_analysis(self.start, self.end, self.mortality, geo, 2015, 2025)
        self.assertTrue(
            all(a["boundary_status"] == "unreliable" for a in result["areas"])
        )

    def test_hierarchy_inputs_cannot_double_count_leaves_and_ancestors(self):
        population = dict(self.start)
        population[("MAD", 25, "male", "ESP")] = 100
        with self.assertRaises(ContractError):
            build_analysis(population, self.end, self.mortality, self.geo, 2015, 2025)

    def test_survival_rejects_nonfinite_and_probabilities_over_one(self):
        bad = dict(self.mortality)
        bad[(2015, 25, "female")] = float("nan")
        with self.assertRaises(ContractError):
            build_analysis(self.start, self.end, bad, self.geo, 2015, 2025)

    def test_birth_extension_uses_baseline_women_and_no_nationality_assignment(self):
        mortality = {
            (y, a, s): 0
            for y in range(2015, 2017)
            for a in range(131)
            for s in ["male", "female"]
        }
        fertility = {(y, a): 100 for y in range(2015, 2017) for a in range(15, 50)}
        result = births_counterfactual(
            {("s", 25, "female", "ESP"): 100}, mortality, fertility, 2015, 2017
        )
        self.assertAlmostEqual(sum(r["expected"] for r in result["children"]), 20)
        self.assertTrue(all("nationality" not in r for r in result["children"]))

    def test_naturalisation_hazards_deplete_exposure_and_preserve_total(self):
        mortality = {
            (y, a, s): 0
            for y in range(2015, 2017)
            for a in range(131)
            for s in ["male", "female"]
        }
        hazards = {
            (y, a, s): 0.5
            for y in range(2015, 2017)
            for a in range(131)
            for s in ["male", "female"]
        }
        result = nationality_scenarios(
            {("s", 25, "female", "EXT"): 100},
            mortality,
            hazards,
            2015,
            2017,
            multipliers=(1,),
        )
        rows = result["scenarios"][0]["adjustments"]
        self.assertEqual(sum(r["EXT"] for r in rows), 75)
        self.assertTrue(all(r["ESP"] + r["EXT"] == 0 for r in rows))

    def test_published_total_reconciliation_covers_children(self):
        result = build_analysis(
            self.start, self.end, self.mortality, self.geo, 2015, 2025
        )
        rows = reconcile(result, [{"area_id": "MAD", "population": 158}], 2025)
        self.assertTrue(rows[0]["passed"])

    def test_official_export_fails_without_empirical_evidence_and_preserves_demo_gate(
        self,
    ):
        result = build_analysis(
            self.start, self.end, self.mortality, self.geo, 2015, 2025
        )
        config = ModelConfig(dataset_kind="official")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ContractError, "official release blocked"):
                write_bundle(result, config, self.geo, {}, tmp)
        self.assertFalse(
            official_release_gate(config, {}, validate_analysis(result, self.geo))[
                "passed"
            ]
        )

    def test_export_is_reproducible_and_respects_geometry_id_and_budget_contract(self):
        result = build_analysis(
            self.start, self.end, self.mortality, self.geo, 2015, 2025
        )
        config = ModelConfig()
        with tempfile.TemporaryDirectory() as tmp:
            geom = {
                "section": {"s": box(-3.7, 40.4, -3.6, 40.5)},
                "city": {"MAD": box(-3.7, 40.4, -3.6, 40.5)},
            }
            one = write_bundle(result, config, self.geo, geom, Path(tmp) / "one")
            two = write_bundle(result, config, self.geo, geom, Path(tmp) / "two")
            self.assertEqual(one, two)
            self.assertLess(one["performance"]["initial_gzip_bytes"], 500000)
            for ref in one["artifacts"].values():
                self.assertEqual(
                    hashlib.sha256(
                        (Path(tmp) / "one" / ref["url"]).read_bytes()
                    ).hexdigest(),
                    ref["sha256"],
                )
            with self.assertRaises(ContractError):
                write_bundle(
                    result,
                    config,
                    self.geo,
                    {"section": {"wrong": box(0, 0, 1, 1)}},
                    Path(tmp) / "bad",
                )


class SourceTests(unittest.TestCase):
    def test_schema_drift_and_raw_sum_mismatch_fail(self):
        schema = json.loads(Path("config/schema-aliases.json").read_text())["schemas"][
            0
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "padron.csv"
            headers = list(schema["aliases"])
            path.write_text(";".join(headers) + "\n01;011;01001;25;2;3;4;5\n")
            facts, excluded, profile = normalize_padron(
                path, schema, "2015-01-01", "fixture"
            )
            self.assertEqual(facts[0]["geography_id"], "2807901001")
            self.assertEqual(profile["total"], 14)
            path.write_text(
                ";".join(headers) + ";SURPRISE\n01;011;01001;25;2;3;4;5;9\n"
            )
            with self.assertRaises(ContractError):
                normalize_padron(path, schema, "2015-01-01", "fixture")

    def test_life_table_units_and_lx_ratios_are_explicit(self):
        rows = [
            {"year": 2015, "age": a, "sex": "female", "lx": v}
            for a, v in [(25, 1000), (26, 900), (27, 800)]
        ]
        result = extract_mortality(rows, "lx", "survivors")
        self.assertAlmostEqual(result[(2015, 25, "female")], 0.1)
        with self.assertRaises(ContractError):
            extract_mortality(rows, "mx", "probability")
        probability = extract_mortality(
            [{"year": 2015, "age": 25, "sex": "female", "qx": 1}], "qx", "per_1000"
        )
        self.assertEqual(probability[(2015, 25, "female")], 0.001)

    def test_annual_jump_diagnostics_do_not_mislabel_jumps_as_moves(self):
        rows = discontinuities(
            [
                {"reference_date": "2015-01-01", "total": 100},
                {"reference_date": "2016-01-01", "total": 120},
            ]
        )
        self.assertTrue(rows[0]["flagged"])

    def test_non_january_window_is_rejected(self):
        with self.assertRaises(ContractError):
            ModelConfig(start_date="2015-02-01")
