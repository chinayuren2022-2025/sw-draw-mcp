"""v2 模块纯 Python 单测（测试桩导入，不连 SolidWorks）。"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

import sw_asm_ref as ar  # noqa: E402
import sw_assembly_full as af  # noqa: E402
import sw_part_dsl  # noqa: E402


class TestTransform(unittest.TestCase):
    def test_identity_translation(self):
        xf = {"rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "translation_mm": [10, 20, 30],
              "scale": 1.0}
        self.assertEqual(ar.apply_point(xf, [1, 2, 3]), [11, 22, 33])
        self.assertEqual(ar.apply_dir(xf, [0, 0, 1]), [0, 0, 1])

    def test_row_vector_convention(self):
        # 组件 X 轴指向装配 Y：rotation 第一行 = 组件 X 轴在装配中的方向
        xf = {"rotation": [[0, 1, 0], [-1, 0, 0], [0, 0, 1]], "translation_mm": [0, 0, 0],
              "scale": 1.0}
        self.assertEqual(ar.apply_point(xf, [5, 0, 0]), [0, 5, 0])
        self.assertEqual(ar.apply_dir(xf, [0, 1, 0]), [-1, 0, 0])

    def test_box_transform_reorders_corners(self):
        xf = {"rotation": [[-1, 0, 0], [0, 1, 0], [0, 0, -1]], "translation_mm": [0, 0, 100],
              "scale": 1.0}
        rec = ar._to_asm_coords({"box_mm": [0, 0, 0, 10, 10, 30]}, xf)
        self.assertEqual(rec["box_mm"], [-10, 0, 70, 0, 10, 100])


class TestMateTables(unittest.TestCase):
    def test_mate_types_match_sw2018_swconst(self):
        # 取自 SW2018 SolidWorks.Interop.swconst.dll 反射（swMateType_e）
        expected = {"coincident": 0, "concentric": 1, "perpendicular": 2, "parallel": 3,
                    "tangent": 4, "distance": 5, "angle": 6, "symmetric": 8,
                    "cam_follower": 9, "gear": 10, "width": 11, "lock_to_sketch": 12,
                    "rack_pinion": 13, "path": 15, "lock": 16, "screw": 17,
                    "linear_coupler": 18, "universal_joint": 19, "coordinate": 20,
                    "slot": 21, "hinge": 22, "slider": 23, "profile_center": 24,
                    "magnetic": 25}
        self.assertEqual(af.MATE_TYPES, expected)

    def test_constrained_status(self):
        self.assertEqual(af.CONSTRAINED_STATUS[2], "under_constrained")
        self.assertEqual(af.CONSTRAINED_STATUS[3], "fully_constrained")


class TestDslNames(unittest.TestCase):
    BASE = {"sketches": [{"name": "s", "plane": "front",
                          "entities": [{"type": "circle", "cx": 0, "cy": 0, "r": 5}]}],
            "features": [{"op": "extrude_boss", "sketch": "s", "depth_mm": 10}]}

    def test_names_accepted(self):
        spec = dict(self.BASE, names=[{"name": "PIN", "ref": {"spec": {"kind": "cylinder"}}}])
        self.assertTrue(sw_part_dsl.dry_run(spec)["valid"])

    def test_names_duplicate_and_missing_ref(self):
        spec = dict(self.BASE, names=[{"name": "A", "ref": {"index": 0}},
                                      {"name": "A", "ref": {"index": 1}},
                                      {"name": "B"}])
        errors = sw_part_dsl.dry_run(spec)["errors"]
        self.assertTrue(any("重复" in e for e in errors))
        self.assertTrue(any("names[2]" in e for e in errors))


class TestImportsV2(unittest.TestCase):
    def test_modules_import(self):
        import sw_doc  # noqa: F401
        import sw_topo  # noqa: F401
        self.assertTrue(callable(ar.mate))


if __name__ == "__main__":
    unittest.main()
