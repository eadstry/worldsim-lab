# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Validate the OpenArm v2 model schema; optionally compare GPU FK against URDF CPU FK."""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import fields
import hashlib
import json
from pathlib import Path


def swap_names(value):
    if isinstance(value, str):
        return value.replace('left', '__SIDE__').replace('right', 'left').replace('__SIDE__', 'right')
    if isinstance(value, list):
        return [swap_names(item) for item in value]
    if isinstance(value, dict):
        return {swap_names(key): swap_names(item) for key, item in value.items()}
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cuda', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    if args.cuda:
        # The pinned public runtime module re-exports scalar values; configure the implementation.
        from curobo._src import runtime
        runtime.cache_dir = str(root / '.local/cache/v2/curobo')
    cfg = json.loads((root / '.local/machine.json').read_text())
    robot_file = Path(cfg['production_snapshot']) / 'runtime/openarm_autodata/shared/autodata_configs/planners/openarm_right.yml'
    import yaml
    data = yaml.safe_load(robot_file.read_text())
    kin = data['robot_cfg']['kinematics']
    for key in ['urdf_path', 'asset_root_path']:
        kin[key] = str((robot_file.parent / kin[key]).resolve())
    for key in ['ee_link', 'self_collision_ignore', 'extra_links', 'cspace']:
        kin[key] = swap_names(kin[key])
    kin['lock_joints'] = {f'openarm_right_joint{i}': 0.0 for i in range(1, 8)}
    kin['lock_joints'].update(openarm_right_finger_joint1=0.0, openarm_left_finger_joint1=0.7)
    kin['cspace']['retract_config'] = [0, 0, 0, 1.5, 0, 0, 0, 0.7]
    kin['extra_collision_spheres'] = {'attached_object': 16}
    from model import convert_robot
    data['robot_cfg'] = convert_robot(data['robot_cfg'])
    kin = data['robot_cfg']['kinematics']
    from curobo._src.robot.loader.kinematics_loader_cfg import KinematicsLoaderCfg
    unsupported = set(kin) - {f.name for f in fields(KinematicsLoaderCfg)}
    assert not unsupported, f'Unsupported v1 fields: {unsupported}'
    from curobo._src.robot.types.cspace_params import CSpaceParams
    unsupported_cspace = set(kin['cspace']) - {f.name for f in fields(CSpaceParams)}
    assert not unsupported_cspace, f'Unsupported v1 cspace fields: {unsupported_cspace}'
    report = dict(schema_passed=True, cuda_validation_performed=False,
                  robot_yaml_sha256=hashlib.sha256(robot_file.read_bytes()).hexdigest(),
                  urdf_sha256=hashlib.sha256(Path(kin['urdf_path']).read_bytes()).hexdigest(),
                  v2_commit=cfg['v2_commit'], tool_frames=kin['tool_frames'])
    if args.cuda:
        import numpy as np
        import torch
        from curobo.kinematics import Kinematics, KinematicsCfg
        from curobo.types import JointState
        from yourdfpy import URDF
        model = Kinematics(KinematicsCfg.from_robot_yaml_file(data))
        q = model.default_joint_position.reshape(1, -1)
        gpu_fk = model.compute_kinematics(JointState.from_position(q, joint_names=model.joint_names))
        gpu_matrix = gpu_fk.tool_poses.get_link_pose(kin['tool_frames'][0]).get_matrix().reshape(4, 4).cpu().numpy()
        urdf = URDF.load(kin['urdf_path'], load_meshes=False, build_scene_graph=True)
        positions = dict(kin['lock_joints'])
        positions.update(zip(model.joint_names, q.flatten().cpu().tolist()))
        urdf.update_cfg(positions)
        cpu_matrix = urdf.get_transform(kin['tool_frames'][0], kin['base_link'])
        error = float(np.max(np.abs(gpu_matrix - cpu_matrix)))
        assert error < 1e-4, f'GPU/URDF FK mismatch: {error}'
        report.update(cuda_validation_performed=True, fk_max_absolute_error=error,
                      active_joint_names=model.joint_names, allocated_mib=torch.cuda.memory_allocated() / 2**20)
    (root / '.local' / ('model-cuda.json' if args.cuda else 'model-schema.json')).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
