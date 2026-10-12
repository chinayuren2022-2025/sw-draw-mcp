"""纯 Python 单测：optics 参数推导。WSL/Linux 可运行。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import optics  # noqa: E402


class TestOptics(unittest.TestCase):
    def test_bk7_f50_d25(self):
        p, msgs = optics.derive_plano_convex(25, 50, "BK7")
        self.assertEqual(p["D"], 25)
        self.assertAlmostEqual(p["R"], 25.84, places=2)
        self.assertGreater(p["t_e"], 0)
        self.assertEqual(p["material"], "BK7")

    def test_diameter_standardized_up(self):
        p, msgs = optics.derive_plano_convex(26, 60, "K9")
        self.assertEqual(p["D"], 30)
        self.assertTrue(any("直径" in m for _, m in msgs))

    def test_unknown_material_raises(self):
        with self.assertRaises(optics.ConstraintError):
            optics.derive_plano_convex(25, 50, "NoSuchGlass")

    def test_impossible_r_raises(self):
        with self.assertRaises(optics.ConstraintError):
            optics.derive_plano_convex(100, 5, "BK7")

    def test_edge_thickness_auto_fix(self):
        p, msgs = optics.derive_plano_convex(50, 40, "SF11")
        self.assertGreaterEqual(p["t_e"], 1.0)
        self.assertTrue(any("边缘厚度" in m for _, m in msgs))


if __name__ == "__main__":
    unittest.main(verbosity=2)
