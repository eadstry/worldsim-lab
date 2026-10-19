# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Align recorded grasp contact windows without importing simulation dependencies."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import h5py
import numpy as np
from scipy.spatial.transform import Rotation


def load(path: Path, episode: str) -> dict:
    with h5py.File(path, 'r') as file:
        data = file['data'][episode]
        keys = ['actions', 'obs/joint_pos', 'obs/left_tcp_pos_env', 'obs/left_tcp_quat_env',
                'obs/cube_pose', 'obs/left_gripper_pos']
        result = {key: data[key][:] for key in keys}
        result['root'] = data['initial_state/articulation/robot/root_pose'][0]
        result['close'] = int(np.flatnonzero(np.diff(result['actions'][:, -1]) < -.2)[0] + 1)
        result['success'] = bool(data.attrs['success'])
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    base = Path(__file__).resolve().parent / '.local/runs'
    pairs = []
    for index in range(5):
        a = load(base / 'v1-baseline-01/episodes.hdf5', f'demo_{index}')
        b = load(base / 'v2-baseline-04' / ('episodes.hdf5' if index < 4 else 'episodes_failed.hdf5'),
                 f'demo_{index if index < 4 else 0}')
        i, j = a['close'], b['close']
        position = float(np.linalg.norm(a['obs/left_tcp_pos_env'][i] - b['obs/left_tcp_pos_env'][j]) * 1000)
        rotation = (Rotation.from_quat(a['obs/left_tcp_quat_env'][i]).inv()
                    * Rotation.from_quat(b['obs/left_tcp_quat_env'][j])).magnitude()
        pairs.append(dict(seed=101 + index, v1_success=a['success'], v2_success=b['success'],
                          v1_close_frame=i, v2_close_frame=j, tcp_difference_mm=position,
                          orientation_difference_deg=float(np.degrees(rotation)),
                          joint_vector_difference_norm_rad=float(np.linalg.norm(a['obs/joint_pos'][i] - b['obs/joint_pos'][j]))))
    rows = []
    assert np.allclose(a['root'][3:], [0, 0, 0, 1]) and np.allclose(b['root'][3:], [0, 0, 0, 1]), 'Root rotation requires a full frame transform'
    for offset in range(-15, 101):
        i, j = a['close'] + offset, b['close'] + offset
        pa, pb = a['obs/left_tcp_pos_env'][i], b['obs/left_tcp_pos_env'][j]
        ca = a['obs/cube_pose'][i, :3] + a['root'][:3]
        cb = b['obs/cube_pose'][j, :3] + b['root'][:3]
        angle = (Rotation.from_quat(a['obs/left_tcp_quat_env'][i]).inv()
                 * Rotation.from_quat(b['obs/left_tcp_quat_env'][j])).magnitude()
        # Reconstruct the applied, already clipped Cartesian targets; not the unclipped goal.
        ta = pa + .02 * a['actions'][i, :3]
        tb = pb + .02 * b['actions'][j, :3]
        rows.append(dict(close_offset_steps=offset, relative_time_s=offset / 30,
                         v1_cube_lift_mm=float((a['obs/cube_pose'][i, 2] - a['obs/cube_pose'][0, 2]) * 1000),
                         v2_cube_lift_mm=float((b['obs/cube_pose'][j, 2] - b['obs/cube_pose'][0, 2]) * 1000),
                         v1_tcp_cube_distance_mm=float(np.linalg.norm(pa - ca) * 1000),
                         v2_tcp_cube_distance_mm=float(np.linalg.norm(pb - cb) * 1000),
                         tcp_difference_mm=float(np.linalg.norm(pa - pb) * 1000),
                         orientation_difference_deg=float(np.degrees(angle)),
                         applied_target_difference_mm=float(np.linalg.norm(ta - tb) * 1000),
                         v1_action_clipped=bool((abs(a['actions'][i, :6]) >= .19999).any()),
                         v2_action_clipped=bool((abs(b['actions'][j, :6]) >= .19999).any()),
                         v1_gripper_rad=float(a['obs/left_gripper_pos'][i, 0]),
                         v2_gripper_rad=float(b['obs/left_gripper_pos'][j, 0])))
    clipping = {}
    for backend, data in [('v1', a), ('v2', b)]:
        clipped = np.flatnonzero((abs(data['actions'][data['close']:data['close'] + 60, :6]) >= .19999).any(1))
        clipping[backend] = dict(first_clipped_step_after_close=int(clipped[0]), clipped_steps_first_60=len(clipped))
    result = dict(evidence_kind='offline_readback_of_GPU_recordings', alignment='first open-to-close command edge',
                  control_dt_s=1 / 30, paired_cases=pairs, clipping=clipping,
                  selected_offsets=[row for row in rows if row['close_offset_steps'] in [0, 10, 12, 15, 20, 40, 60]])
    (args.output / 'contact-analysis.json').write_text(json.dumps(result, indent=2) + '\n')
    with (args.output / 'contact-timeline.csv').open('w') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    figure, axes = plt.subplots(3, 1, figsize=(8, 8), sharex=True, constrained_layout=True)
    time = [row['relative_time_s'] for row in rows]
    for backend, color in [('v1', '#277da1'), ('v2', '#d55e00')]:
        axes[0].plot(time, [row[backend + '_cube_lift_mm'] for row in rows], label=backend, color=color)
        axes[1].plot(time, [row[backend + '_tcp_cube_distance_mm'] for row in rows], label=backend, color=color)
        axes[2].step(time, [int(row[backend + '_action_clipped']) + (0.08 if backend == 'v2' else 0) for row in rows],
                     where='post', label=backend, color=color, alpha=.8)
    for axis in axes:
        axis.axvline(0, color='gray', linestyle='--', linewidth=1)
        axis.grid(alpha=.2)
        axis.legend(loc='upper left')
    axes[0].set_ylabel('Cube lift [mm]')
    axes[1].set_ylabel('TCP-to-cube distance [mm]')
    axes[2].set_ylabel('Any pose action clipped')
    axes[2].set_yticks([0, 1], ['No', 'Yes'])
    axes[2].set_xlabel('Time relative to gripper close command [s]')
    figure.suptitle('Original paired seed 105: divergence during grasp contact')
    figure.savefig(args.output / 'contact-timeline.png', dpi=180)
    plt.close(figure)


if __name__ == '__main__':
    main()
