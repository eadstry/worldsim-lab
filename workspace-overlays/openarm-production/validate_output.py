# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Check recorded success, action/image dimensions and physical placement terminal state."""

import argparse
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("file", type=Path)
args = parser.parse_args()


def rotation(q):
    x, y, z, w = q / np.linalg.norm(q)
    return np.array([
        [1 - 2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
        [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
        [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)],
    ])


report = {"file": str(args.file.resolve()), "episodes": []}
with h5py.File(args.file) as dataset:
    env_name = json.loads(dataset["data"].attrs["env_args"])["env_name"]
    assert "OpenArm" in env_name
    arm = "left" if "Left" in env_name else "right"
    assert len(dataset["data"]), "No episodes exported"
    for name, episode in dataset["data"].items():
        steps = len(episode["actions"])
        assert episode["actions"].shape == (steps, 7)
        assert np.isfinite(episode["actions"][:]).all()
        images = {}
        for camera in ("left_hand_rgb", "right_hand_rgb", "third_person_rgb"):
            image = episode[f"obs/{camera}"]
            assert image.shape == (steps, 480, 640, 3)
            assert image.dtype == np.uint8
            images[camera] = {
                "shape": list(image.shape), "dtype": str(image.dtype),
                "first_frame_mean": float(np.asarray(image[0]).mean()),
                "last_frame_mean": float(np.asarray(image[-1]).mean()),
            }
        cube = episode["states/rigid_object/cube/root_pose"][-1]
        table = episode["states/rigid_object/table/root_pose"][-1]
        velocity = episode["states/rigid_object/cube/root_velocity"][-1]
        table_rot = rotation(table[3:])
        position = table_rot.T @ (cube[:3] - table[:3])
        extent = 0.019 * np.abs(table_rot.T @ rotation(cube[3:])).sum(axis=1)
        inside = all(position[i] - extent[i] >= lower and position[i] + extent[i] <= upper
                     for i, (lower, upper) in enumerate(((0.270, 0.485), (0.130, 0.260))))
        height_error = abs(position[2] - extent[2] - 0.5205)
        joints = episode["states/articulation/robot/joint_position"][-1]
        # The verified articulation resolves left fingers to 14/15 and right fingers to 16/17.
        gripper = abs(float(joints[14 if arm == "left" else 16]))
        linear_speed = float(np.linalg.norm(velocity[:3]))
        angular_speed = float(np.linalg.norm(velocity[3:]))
        terminal_success = bool(inside and height_error <= 0.008 and gripper >= 0.30
                                and linear_speed <= 0.03 and angular_speed <= 0.5)
        report["episodes"].append({
            "name": name, "steps": steps, "recorded_success": bool(episode.attrs["success"]),
            "final_state_success": terminal_success, "inside_pad": bool(inside),
            "height_error_m": float(height_error), "gripper_position_rad": gripper,
            "linear_speed_m_s": linear_speed, "angular_speed_rad_s": angular_speed,
            "images": images,
        })
report["passed"] = all(ep["recorded_success"] and ep["final_state_success"] for ep in report["episodes"])
digest = hashlib.sha256()
with args.file.open("rb") as stream:
    for chunk in iter(lambda: stream.read(4*1024*1024), b""):
        digest.update(chunk)
report["sha256"] = digest.hexdigest()
args.file.with_suffix(".validation.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
assert report["passed"], "Recorded or terminal-state success check failed"
