"""Meaningful host checks for geometry, metric units and incomplete experiment denominators."""
import unittest
import numpy as np
from metrics import BLOCK_CENTER, BLOCK_HALF, TARGET_XY, signed_aabb_clearance, trajectory_metrics, summarize_cells


class MetricTests(unittest.TestCase):
    def test_obstacle_crosses_transfer_but_leaves_endpoints_free(self):
        self.assertLess(signed_aabb_clearance([.5, BLOCK_CENTER[1], .245], [.02]*3), 0)
        for y in (0, TARGET_XY[1]):
            self.assertGreater(signed_aabb_clearance([.5, y, .245], [.035]*3), .07)

    def test_touching_and_penetration_sign(self):
        edge = BLOCK_CENTER + [BLOCK_HALF[0] + .02, 0, 0]
        self.assertAlmostEqual(signed_aabb_clearance(edge, [.02]*3), 0)
        self.assertLess(signed_aabb_clearance(BLOCK_CENTER, [.02]*3), 0)

    def test_metric_units(self):
        q=np.zeros((3,9));q[:,0]=[0,.1,.2]
        tcp=np.zeros((3,7));tcp[:,1]=[0,.05,.1]
        r=trajectory_metrics(q,q,tcp,.02)
        self.assertAlmostEqual(r["joint_path_rad"], .2)
        self.assertAlmostEqual(r["tcp_path_m"], .1)
        self.assertAlmostEqual(r["max_joint_speed_rad_s"], 5)
        self.assertEqual(r["joint_target_rmse_rad"],0)

    def test_runtime_failures_do_not_become_zero_task_success(self):
        row=dict(method="ik",obstacle=False,status="execution_error")
        cell=summarize_cells([row])[0]
        self.assertEqual(cell["planned"],1)
        self.assertEqual(cell["completed"],0)
        self.assertIsNone(cell["task_success_fraction"])

    def test_completed_planning_failures_stay_in_denominator(self):
        result=dict(success=False,collision_free_success=False,planning=[],planner_initialization_s=2,
                    seconds=9,peak_blocker_contact_n=0)
        cell=summarize_cells([dict(method="ik",obstacle=False,status="completed",result=result,process_wall_s=10)])[0]
        self.assertEqual(cell["completed"],1)
        self.assertEqual(cell["task_success_fraction"],0)


if __name__=="__main__":
    unittest.main()
