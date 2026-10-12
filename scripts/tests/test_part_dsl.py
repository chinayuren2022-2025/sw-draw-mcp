"""纯 Python 单测：通用零件 spec DSL 校验与 dry-run。WSL/Linux 可运行。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sw_part_dsl  # noqa: E402


FLANGE = {
    "units": "mm",
    "planes": [{"name": "P1", "type": "offset", "base": "front", "distance_mm": 5}],
    "sketches": [
        {"name": "sk1", "plane": "front",
         "entities": [{"type": "corner_rectangle", "x1": 0, "y1": 0, "x2": 20, "y2": 10},
                      {"type": "circle", "cx": 10, "cy": 5, "r": 3}],
         "dims": [{"kind": "linear", "p1": [0, 0], "p2": [20, 0],
                   "horizontal": True, "text": [10, -2]}],
         "relations": []},
    ],
    "features": [
        {"op": "extrude_boss", "sketch": "sk1", "depth_mm": 5},
        {"op": "fillet", "radius_mm": 1,
         "edge_specs": {"type": "circle", "radius_mm": 3}},
        {"op": "linear_pattern", "seed_feature": "Fillet1",
         "direction1_spec": {"kind": "edge", "type": "line", "near_mm": [0, 0, 0]},
         "d1_spacing_mm": 10, "d1_instances": 2},
    ],
    "checks": {"expect_volume_mm3": 858.6},
    "save": "out/flange.SLDPRT",
}


class TestPartDsl(unittest.TestCase):
    def test_valid_spec(self):
        _, errors = sw_part_dsl.validate_spec(FLANGE)
        self.assertEqual(errors, [])

    def test_dry_run(self):
        r = sw_part_dsl.dry_run(FLANGE)
        self.assertTrue(r["valid"])
        self.assertEqual(r["plane_count"], 1)
        self.assertEqual(r["sketch_count"], 1)
        self.assertEqual([x["op"] for x in r["feature_ops"]],
                         ["extrude_boss", "fillet", "linear_pattern"])

    def test_unknown_entity(self):
        spec = {"sketches": [{"name": "s", "plane": "front",
                              "entities": [{"type": "hyperbola", "x1": 0}]}],
                "features": []}
        _, errors = sw_part_dsl.validate_spec(spec)
        self.assertTrue(any("未知 type" in e for e in errors))

    def test_unknown_op(self):
        spec = {"sketches": [], "features": [{"op": "make_magic"}]}
        _, errors = sw_part_dsl.validate_spec(spec)
        self.assertTrue(any("未知 op" in e for e in errors))

    def test_plane_reference_must_exist(self):
        spec = {"sketches": [{"name": "s", "plane": "P9", "entities": []}],
                "features": []}
        _, errors = sw_part_dsl.validate_spec(spec)
        self.assertTrue(any("plane" in e for e in errors))

    def test_missing_entity_params(self):
        spec = {"sketches": [{"name": "s", "plane": "front",
                              "entities": [{"type": "line", "x1": 0}]}],
                "features": []}
        _, errors = sw_part_dsl.validate_spec(spec)
        self.assertTrue(any("缺参数" in e for e in errors))

    def test_ops_available_covers_checklist_families(self):
        ops = sw_part_dsl.ops_available()
        for expected in ("extrude_boss", "extrude_cut", "revolve_boss", "fillet",
                         "chamfer", "shell", "simple_hole", "hole_wizard",
                         "linear_pattern", "circular_pattern", "mirror_feature",
                         "combine", "ref_plane", "helix", "extruded_surface",
                         "fill_surface", "knit_surface"):
            self.assertIn(expected, ops)


if __name__ == "__main__":
    unittest.main(verbosity=2)
