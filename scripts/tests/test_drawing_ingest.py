# -*- coding: utf-8 -*-
"""drawing_ingest 纯 Python 单测（WSL 可跑，不需要 SolidWorks）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import drawing_ingest

PDF = "/home/zjulin/ai+sw/mm25-p1-1.pdf"


@unittest.skipUnless(os.path.exists(PDF), "mm25-p1-1.pdf 不存在")
class TestDrawingIngest(unittest.TestCase):
    def test_ingest_mm25(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            r = drawing_ingest.ingest(PDF, out_dir=td)
            self.assertGreaterEqual(len(r["images"]), 4)
            texts = " ".join(t["text"] for t in r["texts"])
            self.assertIn("150", texts)
            self.assertIn("SECTION B-B", texts)
            for img in r["images"]:
                self.assertTrue(os.path.exists(img.get("crop") or img["file"]))


if __name__ == "__main__":
    unittest.main()
