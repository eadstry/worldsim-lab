# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Read back seed 105 placement conditions using the unchanged OpenArm pad geometry."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def inspect_episode(path: Path, episode: str, backend: str) -> dict:
    import h5py
    import numpy as np
    from scipy.spatial.transform import Rotation

    with h5py.File(path, 'r') as file:
        data = file['data'][episode]
        cube = data['obs/cube_pose'][:]
        table = data['obs/table_pose'][-1]
        rotation = Rotation.from_quat(table[3:]).as_matrix()
        position = rotation.T @ (cube[-1, :3] - table[:3])
        relative_rotation = rotation.T @ Rotation.from_quat(cube[-1, 3:]).as_matrix()
        # Constants from the unchanged task scene_cfg.py; quaternion storage is XYZW.
        half_extent = .019 * np.abs(relative_rotation).sum(axis=1)
        inside = all(position[i] - half_extent[i] >= low and position[i] + half_extent[i] <= high
                     for i, (low, high) in enumerate([(.270, .485), (.130, .260)]))
        poses = data['states/rigid_object/cube/root_pose'][:]
        initial = data['initial_state/rigid_object/cube/root_pose'][0]
        velocity = data['states/rigid_object/cube/root_velocity'][-1]
        gripper = data['obs/left_gripper_pos'][:, 0]
        bottom = float(position[2] - half_extent[2])
        return dict(backend=backend, seed=105, success=bool(data.attrs['success']),
                    recorded_frames=len(cube), cube_final_position_table_m=position.tolist(),
                    cube_final_projected_half_extent_m=half_extent.tolist(), inside_pad=bool(inside),
                    cube_bottom_height_table_m=bottom, height_condition=abs(bottom - .5205) <= .008,
                    gripper_final_rad=float(gripper[-1]), released=bool(abs(gripper[-1]) >= .30),
                    final_linear_speed_m_s=float(np.linalg.norm(velocity[:3])),
                    final_angular_speed_rad_s=float(np.linalg.norm(velocity[3:])),
                    max_cube_z_world_m=float(poses[:, 2].max()), initial_cube_z_world_m=float(initial[2]),
                    max_lift_above_initial_m=float(poses[:, 2].max() - initial[2]),
                    gripper_min_abs_rad=float(np.abs(gripper).min()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('v1_file', type=Path)
    parser.add_argument('v2_file', type=Path)
    parser.add_argument('--v1-episode', default='demo_4')
    parser.add_argument('--v2-episode', default='demo_0')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = dict(quaternion_convention='xyzw, per OpenArm MDP and recorded poses',
                  evidence_kind='readback_of_runtime_recordings',
                  runs=[inspect_episode(args.v1_file, args.v1_episode, 'v1'),
                        inspect_episode(args.v2_file, args.v2_episode, 'v2')],
                  interpretation='v2 seed 105 fails pad XY containment; lift is small. '
                                 'Missed grasp is consistent with the recording; exact controller/planner cause remains unproven.')
    args.output.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
