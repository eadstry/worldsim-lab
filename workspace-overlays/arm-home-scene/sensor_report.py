"""Validate synchronized RGB, wrist mounting and raw simulated force telemetry."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import h5py
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    subprocess.run([sys.executable, str(Path(__file__).with_name("verify.py")), str(args.run)], check=True)
    with h5py.File(args.run / "episodes.hdf5", "r") as f:
        d = f["data/demo_0"]
        obs = d["obs"]
        frames = len(d["actions"])
        normal = obs["finger_normal_force_w"][:]
        friction = obs["finger_friction_force_w"][:]
        wrench = obs["wrist_joint_wrench"][:]
        time = obs["sensor_time_s"][:]
        assert normal.shape == friction.shape == (frames, 4, 2, 3)
        assert wrench.shape == (frames, 4, 6) and time.shape == (frames, 4)
        assert all(np.isfinite(x).all() for x in (normal, friction, wrench, time))
        assert np.allclose(np.diff(time.ravel()), .005, atol=1e-9)
        phase = np.repeat(obs["phase"][:], 4)
        force = np.linalg.norm(normal.reshape(-1, 2, 3), axis=-1)
        carry_force = np.median(force[phase == 4], axis=0)
        assert (carry_force > .01).all(), "No measured banana contact on both fingers during transfer"
        assert np.max(force[phase == 0]) < .01, "Unexpected object contact before grasp"
        assert np.max(force[phase == 8]) < .01, "Object contact persists after withdrawal"
        assert np.std(wrench.reshape(-1, 6), axis=0).max() > 1e-6, "Frozen wrist wrench"
        hand = obs["hand_pose_w"][:]
        wrist = obs["wrist_pose_ros_w"][:]
        assert hand.shape == wrist.shape == (frames, 7)
        assert np.isfinite(hand).all() and np.isfinite(wrist).all()
        assert np.allclose(np.linalg.norm(wrist[:, 3:], axis=1), 1, atol=1e-4)
        # Independently reconstruct camera position from the moving hand pose.
        offset = np.asarray(d["calibration/wrist"].attrs["offset_pos"])
        q, w = hand[:, 3:6], hand[:, 6:7]
        rotated = offset + 2 * np.cross(q, np.cross(q, offset) + w * offset)
        mount_error = np.linalg.norm(wrist[:, :3] - hand[:, :3] - rotated, axis=1)
        assert mount_error.max() < .001, "Wrist camera pose not synchronized to its physical mount"
        assert np.linalg.norm(np.ptp(wrist[:, :3], axis=0)) > .05, "Wrist camera did not move"
        for camera in ("overview", "detail", "wrist"):
            K = d[f"calibration/{camera}/K"][:]
            assert K.shape == (3, 3) and np.isfinite(K).all() and K[0, 0] > 0 and K[1, 1] > 0
        report = dict(
            frames=frames, rgb_hz=50, force_hz=200, physics_force_samples=frames * 4,
            wrist_mount_max_error_m=float(mount_error.max()),
            median_transfer_finger_normal_N=carry_force.tolist(),
            peak_finger_normal_N=force.max(axis=0).tolist(),
            released_max_finger_normal_N=float(force[phase == 8].max()),
            peak_wrist_reaction_force_N=float(np.linalg.norm(wrench[..., :3], axis=-1).max()),
            peak_wrist_reaction_torque_Nm=float(np.linalg.norm(wrench[..., 3:], axis=-1).max()),
            force_semantics="Finger normal and friction forces on sensing finger, filtered to object, world frame",
            wrench_semantics="Simulated panda_hand incoming-joint reaction at child-side anchor; includes dynamics; not isolated external F/T",
        )
    (args.run / "sensor-verification.json").write_text(json.dumps(report, indent=2))
    t = time.ravel()
    raw_wrench = wrench.reshape(-1, 6)
    raw_friction = friction.reshape(-1, 2, 3)
    columns = np.column_stack((t, force, raw_friction.reshape(-1, 6), raw_wrench))
    np.savetxt(args.run / "forces.csv", columns, delimiter=",", comments="", header=(
        "time_s,left_normal_N,right_normal_N,left_friction_x_N,left_friction_y_N,left_friction_z_N,"
        "right_friction_x_N,right_friction_y_N,right_friction_z_N,Fx_N,Fy_N,Fz_N,Tx_Nm,Ty_Nm,Tz_Nm"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 1, figsize=(11, 7), sharex=True, constrained_layout=True)
    for i, label in enumerate(("Left finger", "Right finger")):
        axes[0].plot(t, force[:, i], linewidth=.8, label=label)
    axes[0].set_ylabel("Normal contact [N]")
    axes[0].set_title("Filtered finger contact and simulated wrist joint reaction (raw 200 Hz)")
    for i, label in enumerate(("Fx", "Fy", "Fz")):
        axes[1].plot(t, raw_wrench[:, i], linewidth=.7, label=label)
    axes[1].set_ylabel("Wrist reaction [N]")
    for i, label in enumerate(("Tx", "Ty", "Tz")):
        axes[2].plot(t, raw_wrench[:, i + 3], linewidth=.7, label=label)
    axes[2].set_ylabel("Wrist reaction [N m]")
    axes[2].set_xlabel("Time since recorded sequence start [s]")
    for axis in axes:
        axis.axvspan(5, 13.5, color="tab:green", alpha=.08)
        axis.axvline(13.5, color="gray", linestyle="--", linewidth=.8)
        axis.legend(loc="upper right", ncol=3)
        axis.grid(alpha=.2)
    fig.savefig(args.run / "forces.png", dpi=160)
    fig.savefig(args.run / "forces.svg")
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
