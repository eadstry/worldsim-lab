# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Add read-only cube-pose telemetry to the frozen task runner for acceptance auditing."""
from pathlib import Path
import hashlib
import json
import sys


def main():
    base = Path(__file__).with_name('task_trials.py')
    original = base.read_text()
    source = original
    edits = [
        ("'reference_index', 'active', 'placed']}",
         "'reference_index', 'active', 'placed', 'geometry_placed', 'cube_quaternion', 'cube_angular_velocity']}"),
        ('            substep_sums = np.zeros((n, 3))',
         "            from collections import deque\n            cube_physics = deque(maxlen=args.physics_hz*10)\n            substep_sums = np.zeros((n, 3))"),
        ('                    env.scene.update(dt=float(env.physics_dt))',
         '''                    env.scene.update(dt=float(env.physics_dt))
                    cube_physics.append(torch.cat((unwrap(cube.data.root_pos_w)-env.scene.env_origins,
                        unwrap(cube.data.root_quat_w), unwrap(cube.data.root_lin_vel_w),
                        unwrap(cube.data.root_ang_vel_w)), -1).detach().cpu().numpy().copy())'''),
        ("                z = unwrap(cube.data.root_pos_w)[:, 2].cpu().numpy()",
         '''                geometry_placed = mdp.cube_placed_on_pad(env,
                    robot_cfg=SceneEntityCfg('robot', joint_names=[active[7]]),
                    max_linear_speed=float('inf'), max_angular_speed=float('inf')).cpu().numpy()
                z = unwrap(cube.data.root_pos_w)[:, 2].cpu().numpy()'''),
        ("('reference_index', np.asarray(indices)), ('active', mask.copy()), ('placed', raw_placed)]:",
         "('reference_index', np.asarray(indices)), ('active', mask.copy()), ('placed', raw_placed),\n"
         "                                   ('geometry_placed', geometry_placed), ('cube_quaternion', unwrap(cube.data.root_quat_w)),\n"
         "                                   ('cube_angular_velocity', unwrap(cube.data.root_ang_vel_w))]:"),
        ("            stacked = {k: np.asarray(v) for k, v in arrays.items()}",
         "            np.savez_compressed(args.output/f'cube-physics-r{repeat}.npz', values=np.asarray(cube_physics),\n"
         "                                physics_dt=float(env.physics_dt), assignments=np.asarray(assignments))\n"
         "            stacked = {k: np.asarray(v) for k, v in arrays.items()}"),
    ]
    for before, after in edits:
        assert source.count(before) == 1, before
        source = source.replace(before, after, 1)
    marker = '    args.output.mkdir(parents=True, exist_ok=False)'
    assert source.count(marker) == 1
    source = source.replace(marker, marker+"\n    (args.output/'diagnostic-integration.json').write_text(json.dumps(_diagnostic_metadata, indent=2))", 1)
    metadata = dict(base_file=str(base), base_sha256=hashlib.sha256(original.encode()).hexdigest(),
                    expanded_sha256=hashlib.sha256(source.encode()).hexdigest(),
                    diagnostic='Read-only position/orientation, raw velocities and geometry-only placement flags; original acceptance and control remain unchanged.')
    # Commit integration metadata immediately after output creation. Simulator
    # shutdown can terminate the process before a caller's finally block runs.
    exec(compile(source, '<task-cube-acceptance-audit>', 'exec'),
         {'__name__': '__main__', '__file__': __file__, '_diagnostic_metadata': metadata})


if __name__ == '__main__':
    main()
