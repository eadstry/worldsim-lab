# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Bound attempts in a process-local production overlay; never edit upstream."""
from __future__ import annotations

import argparse
import builtins
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import sysconfig


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Runtime source boundary changed: ' + old[:90])
    return source.replace(old, new, 1)


def bounded_source(source, attempts, envs):
    if attempts < 1 or envs < 1 or attempts % envs:
        raise ValueError('Attempts must be positive and divisible by environments')
    source = replace_once(source,
        '    while True:\n        try:\n            result = await data_generator.generate(',
        f'    for _capacity_attempt in range({attempts // envs}):\n        try:\n            result = await data_generator.generate(')
    source = replace_once(source, '\n\ndef build_datastream(', '''
    # The batch loop needs one action per environment. Finished producers provide
    # zero relative motion with unchanged gripper, never start another attempt.
    idle = torch.zeros(env.action_space.shape[1:], device=env.device)
    idle[-1] = env.action_manager.action[env_id, -1]
    while True:
        await env_action_queue.put((env_id, idle))
        await env_action_queue.join()


def build_datastream(''')
    source = replace_once(source,
        '    generation_policy_params = task_descriptor.get_generation_policy()',
        '''    generation_policy_params = task_descriptor.get_generation_policy()
    assert generation_policy_params.guarantee_success is False
    assert generation_policy_params.keep_failed is True''')
    # Seed before gym.make/reset, so initialization is also paired across exports.
    source = replace_once(source, '    env = gym.make(env_name, cfg=env_cfg).unwrapped',
        '''    env_cfg.seed = generation_policy_params.seed
    random.seed(generation_policy_params.seed)
    np.random.seed(generation_policy_params.seed)
    torch.manual_seed(generation_policy_params.seed)
    env = gym.make(env_name, cfg=env_cfg).unwrapped''')
    return source


def generator_guard(source):
    source = replace_once(source,
        '    env.recorder_manager.set_success_to_episodes(',
        '''    from terminal_gate import recorded_terminal_success
    terminal_pass = recorded_terminal_success(env, int(env_id))
    buffers.success = bool(buffers.success and terminal_pass)
    env.recorder_manager.set_success_to_episodes(''')
    return source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--production-root', type=Path, required=True)
    parser.add_argument('--gate-root', type=Path, required=True)
    parser.add_argument('--child', action='store_true')
    args, remaining = parser.parse_known_args()
    root = args.production_root.resolve()
    sys.path[:0] = [str(root), str(args.gate_root.resolve())]
    if args.child:
        import compat
        def compile_gate(source, filename, mode, *a, **kw):
            if filename == '<openarm-final-hold>':
                from isaaclab.managers.recorder_manager import RecorderManager
                from async_export import owned_recording_method
                RecorderManager.add_to_episodes = owned_recording_method(RecorderManager.add_to_episodes)
                source = generator_guard(source)
            return builtins.compile(source, filename, mode, *a, **kw)
        compat.compile = compile_gate
        spec = importlib.util.spec_from_file_location('capacity_production_generate', root / 'generate.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        original = module.build_source
        def build(source, cli):
            return original(bounded_source(source, cli.generation_num_trials, cli.num_envs), cli)
        module.build_source = build
        sys.argv = [str(root / 'generate.py'), *remaining]
        module.main()
        return
    cuda = Path(sysconfig.get_paths()['purelib']) / 'nvidia/cu13'
    if (cuda / 'lib').is_dir():
        os.environ['LD_LIBRARY_PATH'] = str(cuda / 'lib') + ':' + os.environ.get('LD_LIBRARY_PATH', '')
    if not os.environ.get('CUDA_HOME') and (cuda / 'bin/nvcc').is_file():
        os.environ['CUDA_HOME'] = str(cuda)
    os.environ['PATH'] = str(Path(sys.executable).parent) + ':' + str(cuda / 'bin') + ':' + os.environ.get('PATH', '')
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    original_popen = subprocess.Popen
    def child(command, *a, **kw):
        command = list(command)
        target = str(root / 'generate.py')
        if target in command:
            index = command.index(target)
            command[index:index + 1] = [str(Path(__file__).resolve()), '--child',
                '--production-root', str(root), '--gate-root', str(args.gate_root.resolve())]
        return original_popen(command, *a, **kw)
    subprocess.Popen = child
    # A completed batch with zero successes is a valid measurement, not a launch
    # error. The harness independently checks exact attempt accounting and files.
    source = replace_once((root / 'run_local.py').read_text(),
        "            assert stats['num_success'] > 0, 'No successful demonstrations'",
        "            assert stats['num_success'] >= 0, 'Invalid success count'")
    source = replace_once(source,
        "                assert export['status'] == 'complete' and output.is_file(), 'Async export is incomplete'",
        "                assert export['status'] == 'complete' and (output.is_file() or stats['num_success'] == 0), 'Async export is incomplete'")
    source = replace_once(source,
        "            assert completed >= args.generation_num_trials, 'Generation target was not reached'",
        "            assert completed == args.generation_num_trials, 'Attempt budget mismatch'")
    sys.argv = [str(root / 'run_local.py'), *remaining]
    namespace = {'__name__': '__main__', '__file__': str(root / 'run_local.py')}
    exec(compile(source, str(root / 'run_local.py'), 'exec'), namespace)


if __name__ == '__main__':
    main()
