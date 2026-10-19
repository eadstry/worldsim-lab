# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Opt-in control/plan trace for diagnosis; never use traced runs as latency benchmarks."""
from __future__ import annotations

import functools
import json
import os
from pathlib import Path


def install(planner_class) -> None:
    from autodata_core.waypoint import MultiWaypoint
    path = Path(os.environ['MVP_METRICS_FILE']).with_suffix('.trace.jsonl')
    tick = 0
    plan_index = 0

    def values(tensor):
        return tensor.detach().cpu().tolist()

    def emit(event, **fields):
        with path.open('a') as file:
            file.write(json.dumps(dict(event=event, tick=tick, **fields)) + '\n')

    execute = MultiWaypoint.execute

    @functools.wraps(execute)
    async def traced_execute(self, datastream, success_term, env_id=0, env_action_queue=None):
        nonlocal tick
        for name, waypoint in self.waypoints.items():
            emit('waypoint', eef=name, target=values(waypoint.pose),
                 actual=values(datastream.get_robot_eef_pose([env_id], name)[0]),
                 joints=values(datastream.get_robot_joint_positions([env_id])[0]),
                 objects={key: values(value[0]) for key, value in datastream.get_object_poses([env_id]).items()},
                 passthrough={key: values(value) for key, value in waypoint.passthrough_action.items()},
                 has_joint_seed=waypoint.joint_seed is not None)
        result = await execute(self, datastream, success_term, env_id, env_action_queue)
        tick += 1
        return result

    MultiWaypoint.execute = traced_execute
    plan = planner_class.update_world_and_plan_motion

    @functools.wraps(plan)
    def traced_plan(self, *args, **kwargs):
        nonlocal plan_index
        emit('plan_start', plan_index=plan_index, expected_attached_object=kwargs.get('expected_attached_object'),
             target=values(kwargs['target_pose']), joint_names=self.datastream.get_robot_joint_names(),
             joints=values(self.datastream.get_robot_joint_positions([self.env_id])[0]),
             objects={key: values(value[0]) for key, value in self.datastream.get_object_poses([self.env_id]).items()})
        result = plan(self, *args, **kwargs)
        emit('plan_end', plan_index=plan_index, success=bool(result))
        plan_index += 1
        return result

    planner_class.update_world_and_plan_motion = traced_plan
    poses = planner_class.get_planned_poses

    @functools.wraps(poses)
    def traced_poses(self):
        result = poses(self)
        emit('planned_poses', plan_index=plan_index - 1, poses=[values(pose) for pose in result])
        return result

    planner_class.get_planned_poses = traced_poses
