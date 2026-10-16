# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Passive capture of real plans, live physics states and a separate RGB camera."""
import functools
import json
import os
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from pxr import Gf, UsdGeom

OUT = Path(os.environ['PLAN_PROBE_DIRECTORY'])
CASE = os.environ['PLAN_PROBE_CASE']
OFFSETS = {'baseline': (0., 0.), 'offset-a': (-.035, .05), 'offset-b': (.035, -.05)}
STATE = {'case': CASE, 'offset_m': OFFSETS[CASE], 'plans': [], 'segments': [], 'frames': [], 'steps': 0}
ENV = None
TRACE = []


def configure_env(cfg):
    from isaaclab.sensors import CameraCfg
    from isaaclab.sim import PinholeCameraCfg
    x, y = OFFSETS[CASE]
    cfg.events.reset_cube.params['pose_range'] = {'x': (x, x), 'y': (y, y)}
    cfg.scene.plan_probe_camera = CameraCfg(
        prim_path='{ENV_REGEX_NS}/PlanProbeCamera', update_period=0.0, height=480, width=640,
        data_types=['rgb'], spawn=PinholeCameraCfg(focal_length=24.0, horizontal_aperture=20.955,
                                                clipping_range=(0.01, 100.0)))
    STATE['cube_default_position_m'] = list(cfg.scene.cube.init_state.pos)
    STATE['scene_configuration'] = 'Original OpenArm config; only cube XY reset fixed at selected in-range offsets. Added render-only camera and curves.'


def curve(name, points, color, width=.003):
    if len(points) < 2:
        return
    c = UsdGeom.BasisCurves.Define(ENV.sim.stage, '/World/PlanProbe/' + name)
    p = np.array(points, dtype=float) + ENV.scene.env_origins[0].cpu().numpy()
    c.CreateTypeAttr('linear')
    c.CreateCurveVertexCountsAttr([len(p)])
    c.CreatePointsAttr([Gf.Vec3f(*map(float, row)) for row in p])
    c.CreateWidthsAttr([width])
    c.SetWidthsInterpolation('constant')
    c.CreateDisplayColorAttr([Gf.Vec3f(*color)])


def eef():
    frame = ENV.scene['ee_frame'].data
    return (frame.target_pos_w[0, 0] - ENV.scene.env_origins[0]).cpu().numpy().tolist()


def capture():
    camera = ENV.scene['plan_probe_camera']
    camera.set_world_poses_from_view(
        ENV.scene.env_origins + torch.tensor([.90, .72, 1.92], device=ENV.device),
        ENV.scene.env_origins + torch.tensor([.50, .10, 1.12], device=ENV.device))
    if TRACE:
        curve('Executed', TRACE[::max(1, len(TRACE)//300)], (.10, .85, .35), .002)
    for _ in range(2):
        ENV.sim.render()
    camera.update(ENV.step_dt, force_recompute=True)
    rgb = camera.data.output['rgb'][0, ..., :3].cpu().numpy()
    filename = f'frame-{len(STATE["frames"]):04d}.jpg'
    Image.fromarray(rgb).save(OUT / filename, quality=88)
    cube = (ENV.scene['cube'].data.root_pos_w[0] - ENV.scene.env_origins[0]).cpu().numpy().tolist()
    STATE['frames'].append({'file': filename, 'step': STATE['steps'], 'time_s': STATE['steps'] * ENV.step_dt,
                            'eef_position_m': eef(), 'cube_position_m': cube,
                            'plan_count': len(STATE['plans']), 'segment_count': len(STATE['segments'])})


def attach_env(env):
    global ENV
    ENV = env
    original = env.step

    @functools.wraps(original)
    def step(*args, **kwargs):
        result = original(*args, **kwargs)
        STATE['steps'] += 1
        TRACE.append(eef())
        if STATE['plans'] and (STATE['steps'] % 20 == 0 or not STATE['frames']):
            capture()
        return result

    env.step = step


def attach_planners(planners):
    for planner in planners.values():
        original = planner.update_world_and_plan_motion

        @functools.wraps(original)
        def plan(*args, _planner=planner, _original=original, **kwargs):
            target = kwargs.get('target_pose', args[0] if args else None)
            record = {'index': len(STATE['plans']), 'start_step': STATE['steps'],
                      'target_pose': target.detach().cpu().numpy().tolist(),
                      'cube_position_m': (ENV.scene['cube'].data.root_pos_w[0]-ENV.scene.env_origins[0]).cpu().numpy().tolist(),
                      'attached_object': kwargs.get('expected_attached_object')}
            STATE['plans'].append(record)
            started = time.perf_counter()
            try:
                result = _original(*args, **kwargs)
                record['success'] = bool(result)
                poses = _planner.get_planned_poses() if result else []
                xyz = np.array([p[:3, 3].detach().cpu().numpy() for p in poses])
                record['eef_positions_m'] = xyz.tolist()
                record['path_length_m'] = float(np.linalg.norm(np.diff(xyz, axis=0), axis=1).sum()) if len(xyz)>1 else 0.
                if len(xyz)>1:
                    curve(f'Transit{record["index"]}', xyz[::max(1,len(xyz)//250)], (1., .38, .06))
                return result
            except BaseException as exc:
                record['error'] = f'{type(exc).__name__}: {exc}'
                raise
            finally:
                record['planning_wall_seconds_including_capture_hook'] = time.perf_counter()-started
                (OUT/'probe.json').write_text(json.dumps(STATE, indent=2))

        planner.update_world_and_plan_motion = plan


def attach_algorithm(algorithm):
    original = algorithm.plan_subtask_trajectory

    @functools.wraps(original)
    def trajectory(*args, **kwargs):
        result = original(*args, **kwargs)
        if result is not None:
            waypoints, is_mp = result
            xyz = [w.pose[:3, 3].detach().cpu().numpy().tolist() for w in waypoints]
            record = {'index': len(STATE['segments']), 'start_step': STATE['steps'],
                      'kind': 'curobo_transit' if is_mp else 'skill_replay', 'eef_positions_m': xyz}
            STATE['segments'].append(record)
            if not is_mp:
                curve(f'Skill{record["index"]}', xyz[::max(1,len(xyz)//250)], (.10, .65, 1.))
        return result

    algorithm.plan_subtask_trajectory = trajectory


def finish():
    STATE['actual_eef_positions_m'] = TRACE
    STATE['scope'] = 'Real cuRobo planning and AutoData action execution. Curves and camera are render-only; no training or general success-rate claim.'
    (OUT/'probe.json').write_text(json.dumps(STATE, indent=2))
