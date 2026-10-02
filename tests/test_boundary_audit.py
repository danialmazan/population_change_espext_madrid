import importlib.util
import unittest

from madrid_demography.boundary_audit import classify


@unittest.skipUnless(
    importlib.util.find_spec("shapely"), "install audit-gis extra for spatial checks"
)
class BoundaryTests(unittest.TestCase):
    def test_split_is_exact_union_candidate(self):
        from shapely.geometry import box

        result = classify(
            {"A": box(0, 0, 100, 100)},
            {"B": box(0, 0, 50, 100), "C": box(50, 0, 100, 100)},
        )
        self.assertEqual(result["component_counts"], {"exact_aggregate_candidate": 1})
        self.assertEqual(result["components"][0]["old_mutual_overlap"], 1)

    def test_equal_id_with_redrawn_geometry_is_not_unchanged(self):
        from shapely.geometry import box

        result = classify({"A": box(0, 0, 100, 100)}, {"A": box(10, 0, 110, 100)})
        self.assertEqual(result["component_counts"], {"redrawn_candidate": 1})

    def test_renumbering_does_not_remove_comparable_polygon(self):
        from shapely.geometry import box

        result = classify({"A": box(0, 0, 100, 100)}, {"B": box(0, 0, 100, 100)})
        self.assertEqual(result["component_counts"], {"renumbered_candidate": 1})
