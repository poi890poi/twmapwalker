"""Pixel-graph cases that previously made ordinary bends look like branches."""
import unittest
import numpy as np
from tools.contour_topology_trial import graph_degree, thin


class ContourGraphTests(unittest.TestCase):
    def assert_graph(self, pixels, endpoints, branches):
        skeleton = thin(pixels)
        degree = graph_degree(skeleton)
        self.assertEqual(int((skeleton & (degree == 1)).sum()), endpoints)
        self.assertEqual(int((skeleton & (degree >= 3)).sum()), branches)

    def test_bend_is_not_a_branch(self):
        pixels = np.zeros((12,12),bool)
        pixels[2:8,5] = True
        pixels[7,5:10] = True
        for turns in range(4):
            self.assert_graph(np.rot90(pixels,turns),2,0)

    def test_diagonal_stays_connected(self):
        self.assert_graph(np.eye(12,dtype=bool),2,0)

    def test_real_junction_remains_a_branch(self):
        pixels = np.zeros((12,12),bool)
        pixels[2:10,5] = True
        pixels[5,5:10] = True
        self.assert_graph(pixels,3,1)

    def test_closed_loop_has_no_endpoints(self):
        pixels = np.zeros((12,12),bool)
        pixels[2,2:10] = pixels[9,2:10] = True
        pixels[2:10,2] = pixels[2:10,9] = True
        self.assert_graph(pixels,0,0)


if __name__ == '__main__':unittest.main()
