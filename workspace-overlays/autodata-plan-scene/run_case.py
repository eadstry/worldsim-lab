# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Run an actual AutoData episode with passive scene/plan capture hooks."""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--workspace', type=Path, required=True)
parser.add_argument('--directory', type=Path, required=True)
parser.add_argument('--case', choices=('baseline', 'offset-a', 'offset-b'), required=True)
args = parser.parse_args()
args.directory.mkdir(parents=True, exist_ok=False)
source_paths = list((args.workspace / 'AutoData/autodata_core').rglob('*.py'))
source_paths += list((args.workspace / 'AutoData/autodata_interfaces').rglob('*.py'))
source_paths += list((args.workspace / 'workspace-overlays/openarm-production').glob('*.py'))
source_paths += list((args.workspace / 'workspace-overlays/openarm-production/runtime/openarm_autodata').rglob('*.py'))
source_paths += [args.workspace / 'AutoData/scripts/generate_dataset.py', Path(__file__), Path(__file__).with_name('scene_probe.py')]
source_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
(args.directory / 'source-sha256.json').write_text(json.dumps(source_hashes, indent=2))
os.environ['PLAN_PROBE_DIRECTORY'] = str(args.directory.resolve())
os.environ['PLAN_PROBE_CASE'] = args.case
sys.path.insert(0, str(args.workspace / 'workspace-overlays/openarm-production'))
import generate

original_build = generate.build_source


def build(source, options):
    source = original_build(source, options)
    anchor = '    env = gym.make(env_name, cfg=env_cfg).unwrapped'
    assert source.count(anchor) == 1
    source = source.replace(anchor, '''    from scene_probe import configure_env, attach_env
    configure_env(env_cfg)
''' + anchor + '\n    attach_env(env)', 1)
    anchor = '        alg_kwargs["motion_planners"] = motion_planners'
    assert source.count(anchor) == 1
    source = source.replace(anchor, anchor + '''
        from scene_probe import attach_planners
        attach_planners(motion_planners)
''', 1)
    anchor = '    algorithm = get_algorithm(args_cli.alg, **alg_kwargs)'
    assert source.count(anchor) == 1
    source = source.replace(anchor, anchor + '''
    from scene_probe import attach_algorithm
    attach_algorithm(algorithm)
''', 1)
    return source


generate.build_source = build
configs = args.workspace / 'workspace-overlays/openarm-production/runtime/openarm_autodata/tasks/pick_place/autodata_configs'
import yaml
task = yaml.safe_load((configs / 'tasks/openarm_bimanual_left_pick_place.yaml').read_text())
task['generation_policy'].update(seed=101, guarantee_success=False, keep_failed=True, max_num_failures=25)
task_path = args.directory / 'task.yaml'
task_path.write_text(yaml.safe_dump(task))
sys.argv = ['generate.py', '--autodata-root', str(args.workspace / 'AutoData'), '--arm', 'left',
            '--input_file', str(args.workspace / 'workspace-overlays/openarm-production/runtime/inputs/openarm_left_fixture_clearance_source.hdf5'),
            '--output_file', str(args.directory / 'episodes.hdf5'), '--num_envs', '1',
            '--generation_num_trials', '1', '--task_descriptor', str(task_path), '--final-hold-steps', '60']
try:
    generate.main()
finally:
    if 'scene_probe' in sys.modules:
        sys.modules['scene_probe'].finish()
    changed = [str(p) for p in source_paths if hashlib.sha256(p.read_bytes()).hexdigest() != source_hashes[str(p)]]
    (args.directory / 'source-stability.json').write_text(json.dumps({'unchanged': not changed, 'changed_paths': changed}))
