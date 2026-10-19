# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Apply the existing left-arm recorded terminal-state predicate before export."""
from __future__ import annotations


def terminal_success(cube, table, velocity, joints):
    import numpy as np

    def rotation(q):
        norm = np.linalg.norm(q)
        if not np.isfinite(norm) or norm <= 0:
            raise ValueError('Invalid terminal quaternion')
        x, y, z, w = q / norm
        return np.array([
            [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
            [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
            [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)],
        ])

    if not all(np.isfinite(x).all() for x in (cube, table, velocity, joints)):
        return False
    table_rot = rotation(table[3:])
    position = table_rot.T @ (cube[:3] - table[:3])
    extent = .019 * np.abs(table_rot.T @ rotation(cube[3:])).sum(axis=1)
    inside = all(position[i] - extent[i] >= lower and position[i] + extent[i] <= upper
                 for i, (lower, upper) in enumerate(((.270, .485), (.130, .260))))
    return bool(inside and abs(position[2] - extent[2] - .5205) <= .008
                and abs(float(joints[14])) >= .30
                and np.linalg.norm(velocity[:3]) <= .03 and np.linalg.norm(velocity[3:]) <= .5)


def recorded_terminal_success(env, env_id):
    """Check the exact last stored frame, rather than the live next simulation tick."""
    data = env.recorder_manager._episodes[int(env_id)].data

    def last(value):
        # Only tiny terminal state vectors are copied, never RGB trajectories.
        return value[-1].detach().cpu().numpy()

    state = data['states']
    passed = terminal_success(last(state['rigid_object']['cube']['root_pose']),
                              last(state['rigid_object']['table']['root_pose']),
                              last(state['rigid_object']['cube']['root_velocity']),
                              last(state['articulation']['robot']['joint_position']))
    from telemetry import _active
    if _active is not None:
        _active.emit('recorded_terminal_acceptance', env_id=int(env_id), passed=passed)
    return passed


def guarded_source(source):
    anchor = '    env.recorder_manager.set_success_to_episodes('
    if source.count(anchor) != 1:
        raise ValueError('Generator export boundary changed; review terminal gate')
    return source.replace(anchor, '''    from terminal_gate import recorded_terminal_success
    buffers.success = buffers.success and recorded_terminal_success(env, int(env_id))
''' + anchor, 1)
