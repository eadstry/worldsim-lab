"""Host-only experiment definitions and metrics; all attempted cases stay in the denominator."""
import numpy as np

PICK_POSITIONS = ((.5, 0.0), (.49, .01), (.51, -.01))
TARGET_XY = (.5, -.3)
BLOCK_CENTER = np.array([.5, -.15, .16])
BLOCK_HALF = np.array([.08, .02, .16])


def signed_aabb_clearance(center, half_extent):
    gap = np.abs(np.asarray(center) - BLOCK_CENTER) - np.asarray(half_extent) - BLOCK_HALF
    return float(np.linalg.norm(np.maximum(gap, 0)) + min(float(gap.max()), 0))


def trajectory_metrics(joints, joint_targets, tcp, dt=.02):
    joints, joint_targets, tcp = map(np.asarray, (joints, joint_targets, tcp))
    dq = np.diff(joints[:, :7], axis=0)
    return dict(joint_path_rad=float(np.linalg.norm(dq, axis=-1).sum()),
                tcp_path_m=float(np.linalg.norm(np.diff(tcp[:, :3], axis=0), axis=-1).sum()),
                max_joint_speed_rad_s=float(np.abs(dq / dt).max()),
                joint_target_rmse_rad=float(np.sqrt(np.mean((joint_targets[:, :7] - joints[:, :7])**2))))


def summarize_cells(cases):
    result = []
    for obstacle in (False, True):
        for method in ("ik", "curobo"):
            rows = [c for c in cases if c["method"] == method and c["obstacle"] == obstacle]
            completed = [c for c in rows if c["status"] == "completed"]
            n, done = len(rows), len(completed)
            successes = sum(bool(c["result"]["success"]) for c in completed)
            safe = sum(bool(c["result"]["collision_free_success"]) for c in completed)
            plans = [p["synchronized_request_s"] for c in completed for p in c["result"]["planning"] if "synchronized_request_s" in p]
            result.append(dict(method=method, obstacle=obstacle, planned=n, completed=done,
                task_successes=successes, collision_free_successes=safe,
                task_success_fraction=successes/n if n and done==n else None,
                collision_free_fraction=safe/n if n and done==n else None,
                mean_planning_s=float(np.mean(plans)) if plans else None,
                mean_initialization_s=float(np.mean([c["result"]["planner_initialization_s"] for c in completed])) if done else None,
                mean_sim_seconds=float(np.mean([c["result"]["seconds"] for c in completed])) if done else None,
                mean_process_wall_s=float(np.mean([c["process_wall_s"] for c in completed])) if done else None,
                peak_blocker_contact_n=max([c["result"]["peak_blocker_contact_n"] for c in completed], default=0)))
    return result
