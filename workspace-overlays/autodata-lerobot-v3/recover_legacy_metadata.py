"""Recover a checksum-bound OpenArm schema from archived runtime joint tables.

This is explicitly historical recovery, not a claim that names were recorded in
the original HDF5. Raw HDF5 bytes are never changed.
"""
import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import h5py
import numpy as np

sys.path.append(str(Path(__file__).resolve().parents[1] / 'openarm-production'))
from dataset_metadata import openarm_schema


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024**2), b''):
            h.update(block)
    return h.hexdigest()


def joint_table(text):
    rows = {}
    for index, name in re.findall(r'^\|\s*(\d+)\s*\|\s*(openarm_\w+)\s*\|', text, re.M):
        index = int(index)
        if index in rows and rows[index] != name:
            raise ValueError('Conflicting runtime joint tables')
        rows[index] = name
    if set(rows) != set(range(18)):
        raise ValueError('Expected one complete indexed 18-joint runtime table')
    return [rows[i] for i in range(18)]


def recover(source_path, log_path, scale, robot_urdf, runtime_report=None):
    names = joint_table(Path(log_path).read_text())
    types = {j.attrib['name']: j.attrib['type'] for j in ET.parse(robot_urdf).findall('joint')}
    if any(types.get(name) not in ('revolute', 'continuous') for name in names):
        raise ValueError('The archived robot asset does not verify radian units for every recorded joint')
    checks = []
    defaults = None
    with h5py.File(source_path, 'r') as f:
        env = json.loads(f['data'].attrs['env_args'])
        name = env['env_name']
        arm = 'left' if '-Left-' in name else 'right'
        if name != f'Isaac-PickPlace-Cube-OpenArm-Bimanual-{arm.title()}-IK-Rel-v0' or f.attrs.get('format_version') != 1:
            raise ValueError('Recovery supports only the identified OpenArm relative IK / XYZW source')
        for episode, ep in f['data'].items():
            post = ep['states/articulation/robot/joint_position'][:]
            pre = np.concatenate([ep['initial_state/articulation/robot/joint_position'][:], post[:-1]])
            observed = ep['obs/joint_pos'][:]
            offsets = pre - observed
            if defaults is None:
                defaults = offsets[0].astype(float)
            np.testing.assert_allclose(offsets, np.broadcast_to(defaults, offsets.shape), rtol=0, atol=2e-6)
            finger_index = names.index(f'openarm_{arm}_finger_joint1')
            np.testing.assert_allclose(pre[:, finger_index], ep[f'obs/{arm}_gripper_pos'][:, 0], rtol=0, atol=2e-6)
            np.testing.assert_allclose(ep['processed_actions'][:, :6], ep['actions'][:, :6] * np.asarray(scale),
                                       rtol=1e-6, atol=1e-7)
            # The controlled elbow and two gripper defaults distinguish this actual
            # interleaved articulation order from a left-arm-then-right-arm guess.
            if arm == 'left':
                np.testing.assert_allclose(defaults[names.index('openarm_left_joint4')], 1.5, atol=1e-6)
                np.testing.assert_allclose(defaults[names.index('openarm_right_joint4')], 0.0, atol=1e-6)
            checks.append(dict(episode=episode, frames=len(post), default_offsets='matched', gripper_column='matched',
                               action_physical_scale='matched'))
    evidence = dict(kind='historical_recovery', runtime_joint_table=str(Path(log_path).resolve()),
                    runtime_joint_table_sha256=digest(log_path), numeric_cross_checks=checks,
                    robot_urdf=str(Path(robot_urdf).resolve()), robot_urdf_sha256=digest(robot_urdf),
                    limitation='Archived table is from another run of this robot profile, not metadata captured in the original HDF5',
                    action_scale_source='Explicit caller-supplied scale from archived OpenArm controller configuration')
    schema = openarm_schema(names, arm, scale, defaults.tolist(), evidence)
    schema['articulations']['robot']['default_joint_velocities'] = [0.0] * 18
    if runtime_report is not None:
        report = json.loads(Path(runtime_report).read_text())
        if report.get('status') != 'passed':
            raise ValueError('Runtime confirmation did not pass')
        actual = report['semantic_metadata']
        if actual['articulations']['robot']['joint_names'] != names:
            raise ValueError('Archived and live runtime joint order differ')
        np.testing.assert_allclose(actual['articulations']['robot']['default_joint_positions'], defaults, rtol=0, atol=2e-6)
        for path, spec in schema['fields'].items():
            if actual['fields'][path]['names'] != spec['names'] or actual['fields'][path]['units'] != spec['units']:
                raise ValueError(f'Archived and live runtime semantic labels differ: {path}')
        schema['evidence']['live_asset_confirmation'] = dict(report=str(Path(runtime_report).resolve()),
                                                           sha256=digest(runtime_report),
                                                           scope=report['scope'])
    return dict(source_sha256=digest(source_path), semantic_metadata=schema)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('runtime_log', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--pose-scale', type=float, nargs=6, required=True)
    parser.add_argument('--robot-urdf', type=Path, required=True)
    parser.add_argument('--runtime-report', type=Path)
    args = parser.parse_args()
    result = recover(args.source, args.runtime_log, args.pose_scale, args.robot_urdf, args.runtime_report)
    with args.output.open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
