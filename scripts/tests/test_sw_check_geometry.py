"""纯 Python 单测：草图开环/自交几何算法。WSL/Linux 可运行。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sw_check  # noqa: E402  (顶层不 import pywin32)


class FakeSeg:
    def __init__(self, t, p1, p2, length=None):
        self._t, self._p1, self._p2, self._length = t, p1, p2, length

    def GetType(self):
        return self._t

    def GetStartPoint2(self):
        return self._p1

    def GetEndPoint2(self):
        return self._p2

    def GetLength(self):
        return self._length


def seg(p1, p2):
    return FakeSeg(0, (p1[0], p1[1], 0.0), (p2[0], p2[1], 0.0))


class TestGeometry(unittest.TestCase):
    def test_closed_rectangle_no_open_loop(self):
        rect = [seg((0, 0), (1, 0)), seg((1, 0), (1, 1)),
                seg((1, 1), (0, 1)), seg((0, 1), (0, 0))]
        self.assertEqual(sw_check.open_loops(rect), [])

    def test_open_chain_two_endpoints(self):
        chain = [seg((0, 0), (1, 0)), seg((1, 0), (1, 1))]
        odd = sw_check.open_loops(chain)
        self.assertEqual(len(odd), 2)

    def test_crossing_lines_detected(self):
        x = [seg((0, 0), (2, 2)), seg((0, 2), (2, 0))]
        hits = sw_check.segment_self_intersections(x)
        self.assertEqual(len(hits), 1)
        self.assertAlmostEqual(hits[0][0], 1.0, places=6)

    def test_shared_endpoint_not_self_intersection(self):
        l = [seg((0, 0), (1, 1)), seg((1, 1), (2, 0))]
        self.assertEqual(sw_check.segment_self_intersections(l), [])

    def test_boxes_overlap(self):
        self.assertTrue(sw_check.boxes_overlap([0, 0, 0, 1, 1, 1], [0.5, 0.5, 0.5, 2, 2, 2]))
        self.assertFalse(sw_check.boxes_overlap([0, 0, 0, 1, 1, 1], [1.1, 0, 0, 2, 1, 1]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
