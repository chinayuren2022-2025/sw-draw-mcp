# -*- coding: utf-8 -*-
"""model_view_compare 纯 Python 单测（不需要 SolidWorks）。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_pip = "/home/zjulin/ai+sw/.pip-deps"
if os.path.isdir(_pip):
    sys.path.insert(0, _pip)

try:
    import cv2
    import numpy as np
    HAS_CV = True
except Exception:
    HAS_CV = False

if HAS_CV:
    import model_view_compare


@unittest.skipUnless(HAS_CV, "opencv 不可用")
class TestModelViewCompare(unittest.TestCase):
    def test_compare_pair(self):
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, "a.png")
            b = os.path.join(td, "b.png")
            ca = np.full((200, 300, 3), 255, np.uint8)
            ca[50:150, 100:200] = 0
            cb = ca.copy()
            cb[50:150, 100:200] = 0
            cv2.imwrite(a, ca)
            cv2.imwrite(b, cb)
            r = model_view_compare.compare_pair(a, b, "test", td)
            self.assertTrue(os.path.exists(r["side_by_side"]))
            self.assertIn("cv_enabled", r)
            self.assertFalse(r["cv_enabled"])
            # 可选 CV 分支不应让默认路径抛异常
            r2 = model_view_compare.compare_pair(a, b, "test2", td, enable_cv=True)
            self.assertTrue(os.path.exists(r2["side_by_side"]))


if __name__ == "__main__":
    unittest.main()
