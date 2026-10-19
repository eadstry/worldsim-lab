#!/usr/bin/env python3
"""Validate, resolve or launch workspace-owned AutoData / Arena adapters."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / 'workspace-overlays/shared_config'
sys.path.insert(0, str(EXTENSION))
from shared_config.config import resolve  # noqa: E402


def plan(config, mode, run_dir, python, input_file=None, output_file=None, device='cuda:0'):
    snapshot = resolve(config)
    required_source = ROOT / 'AutoData/openarm_autodata/tasks/pick_place/configs/left_env_cfg.py'
    if not required_source.is_file():
        raise ValueError('Shared runtime source missing: ' + str(required_source) +
                         '; this package is not provided by the pinned AutoData commit. '
                         'See docs/version-management.md before starting a simulation.')
    cfg = snapshot['experiment']
    c, g, e = cfg['common'], cfg['generation'], cfg['evaluation']
    run_dir = Path(run_dir).resolve()
    snapshot['mode'] = mode
    snapshot['effective_seed'] = c['seed'] if mode == 'generate' else e['seed']
    snapshot['device'] = device
    snapshot['sources'] = {}
    for name in ('AutoData', 'IsaacLab-Arena'):
        snapshot['sources'][name] = subprocess.check_output(
            ['git', '-C', str(ROOT / name), 'rev-parse', 'HEAD'], text=True).strip()
    # Include the actual working tree, since HEAD alone misses local OpenArm changes.
    paths = list((ROOT / 'AutoData/openarm_autodata').rglob('*'))
    paths += list(EXTENSION.rglob('*.py'))
    snapshot['source_hashes'] = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(paths) if p.is_file() and '__pycache__' not in p.parts
    }
    base = [python, '-u']
    common_args = ['--enable_cameras', '--kit_args', '--enable omni.usd.schema.omni_lens_distortion',
                   '--viz', 'none', '--device', device]
    if mode == 'generate':
        if not input_file or not output_file:
            raise ValueError('generate requires --input and --output HDF5 paths')
        command = base + [str(ROOT / 'AutoData/scripts/generate_dataset.py'),
            '--env_module', 'shared_config.generation', '--env_name', c['gym_id'], '--alg', 'skillgen',
            '--task_descriptor', str(run_dir / 'task_descriptor.json'),
            '--embodiment', str(run_dir / 'embodiment.json'), '--env_profile', str(run_dir / 'env_profile.json'),
            '--num_envs', str(g['num_envs']), '--input_file', str(Path(input_file).resolve()),
            '--output_file', str(Path(output_file).resolve())] + common_args
        cwd = ROOT / 'AutoData'
    else:
        command = base + ['-m', 'isaaclab_arena.evaluation.policy_runner',
            '--external_environment_class_path', 'shared_config.arena:CompatibleOpenArmEnvironment',
            '--seed', str(e['seed']),
            '--num_envs', str(e['num_envs']), '--num_episodes', str(e['num_episodes']),
            '--policy_type', e['policy_type'], '--output_base_dir', str(run_dir / 'evaluation')] + common_args
        for key, value in e['policy_args'].items():
            command += ['--' + key, str(value)]
        # Arena's environment-specific flags belong to its registered subparser.
        command += ['openarm_left_pick_place', '--openarm_episode_length_s', str(e['episode_length_s'])]
        cwd = ROOT / 'IsaacLab-Arena'
    snapshot['launch'] = {'argv': command, 'cwd': str(cwd)}
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['validate', 'resolve', 'run'])
    parser.add_argument('config', type=Path)
    parser.add_argument('--mode', choices=['generate', 'evaluate'], default='evaluate')
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--python', default='/isaac-sim/python.sh', help='Interpreter inside the configured GPU container')
    parser.add_argument('--device', default='cuda:0')
    parser.add_argument('--input')
    parser.add_argument('--output')
    args = parser.parse_args()
    if args.action == 'validate':
        print(json.dumps(resolve(args.config), indent=2))
        return
    if args.run_dir is None:
        parser.error('--run-dir is required for resolve/run; use a fresh directory for each run')
    snapshot = plan(args.config, args.mode, args.run_dir, args.python, args.input, args.output, args.device)
    if args.action == 'run' and args.mode == 'generate':
        if not Path(args.input).is_file():
            raise ValueError('Input dataset does not exist')
        if Path(args.output).exists():
            raise ValueError('Refusing to overwrite an output dataset')
    # No simulator starts during validation or resolution.
    args.run_dir.mkdir(parents=True, exist_ok=False)
    def write(name, data):
        (args.run_dir / name).write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')
    write('resolved_config.json', snapshot)
    for name, data in snapshot['native'].items():
        write(name + '.json', data)  # JSON is also valid YAML for upstream from_yaml readers.
    print(json.dumps(snapshot['launch'], indent=2), flush=True)
    if args.action == 'resolve':
        return
    env = os.environ.copy()
    env['PYTHONPATH'] = os.pathsep.join([str(EXTENSION), str(ROOT / 'AutoData'),
                                      str(ROOT / 'IsaacLab-Arena'), env.get('PYTHONPATH', '')])
    env['WORLDSIM_RESOLVED_CONFIG'] = str((args.run_dir / 'resolved_config.json').resolve())
    env['WORLDSIM_AUTODATA_ROOT'] = str(ROOT / 'AutoData')
    result = subprocess.run(snapshot['launch']['argv'], cwd=snapshot['launch']['cwd'], env=env)
    write('process_result.json', {'returncode': result.returncode, 'task_contract_hash': snapshot['task_contract_hash']})
    sys.exit(result.returncode)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError) as error:
        sys.exit(str(error))
