import unittest
import numpy as np
import mujoco
from geometry import compose_visual_frames

class GeometryTests(unittest.TestCase):

    def test_matches_mujoco_rigid_composition(self):
        rng = np.random.default_rng(5)
        for _ in range(100):
            body = rng.normal(size=7)
            body[3:] /= np.linalg.norm(body[3:])
            local = rng.normal(size=7)
            local[3:] /= np.linalg.norm(local[3:])
            position, quaternion = compose_visual_frames(body[None], local[:3], local[3:])
            rotated = np.empty(3)
            expected = np.empty(4)
            mujoco.mju_rotVecQuat(rotated, local[:3], body[3:])
            mujoco.mju_mulQuat(expected, body[3:], local[3:])
            np.testing.assert_allclose(position[0], body[:3] + rotated, atol=1e-12)
            self.assertAlmostEqual(abs(float(quaternion[0] @ expected)), 1, places=12)

    def test_sign_continuity_and_invalid_input(self):
        poses = np.array([[0, 0, 0, 1, 0, 0, 0], [0, 0, 0, -1, 0, 0, 0]], dtype=float)
        _, q = compose_visual_frames(poses, [0, 0, 0], [1, 0, 0, 0])
        np.testing.assert_array_equal(q[0], q[1])
        with self.assertRaises(ValueError):
            compose_visual_frames(np.zeros((2, 7)), [0, 0, 0], [1, 0, 0, 0])
if __name__ == '__main__':
    unittest.main()
