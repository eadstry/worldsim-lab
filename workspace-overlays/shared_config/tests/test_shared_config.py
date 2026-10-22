"""Host checks for contract propagation and launch planning; no simulation imports."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'workspace-overlays/shared_config'))
from shared_config.config import read, resolve
from shared_config.runtime import apply_common

spec = importlib.util.spec_from_file_location('launcher', ROOT / 'scripts/shared-config.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        for source in (ROOT / 'config/openarm').glob('*.json'):
            (self.folder / source.name).write_bytes(source.read_bytes())
        self.path = self.folder / 'experiment.json'
        self.cfg = read(self.path)

    def save(self):
        self.path.write_text(json.dumps(self.cfg))

    def test_scales_and_seed_derived_once(self):
        self.cfg['common']['action']['position_scale_m'] = 0.05
        self.cfg['common']['seed'] = 45
        self.save()
        resolved = resolve(self.path)
        self.assertEqual(resolved['native']['embodiment']['action_layout']['position_action_scale'], 0.05)
        self.assertEqual(resolved['native']['task_descriptor']['generation_policy']['seed'], 45)

    def test_shared_reset_and_success_applied_in_both_modes(self):
        self.cfg['common']['reset_pose_range']['x'] = [-0.1, 0.2]
        self.cfg['common']['success']['max_linear_speed'] = 0.01
        self.save()
        common = resolve(self.path)['experiment']['common']
        def fake_cfg():
            return NS(actions=NS(left_arm_action=NS(scale=None)),
                      events=NS(reset_cube=NS(params={})),
                      terminations=NS(success=NS(params={'robot_cfg': 'left-finger'})))
        generation = apply_common(fake_cfg(), common, 1)
        evaluation = apply_common(fake_cfg(), common, 11)
        self.assertEqual(generation.events.reset_cube.params, evaluation.events.reset_cube.params)
        self.assertEqual(generation.events.reset_cube.params['pose_range']['x'], (-0.1, 0.2))
        self.assertEqual(generation.terminations.success.params, evaluation.terminations.success.params)
        self.assertEqual(generation.terminations.success.params['robot_cfg'], 'left-finger')
        self.assertEqual(evaluation.terminations.success.params['max_linear_speed'], 0.01)
        self.assertEqual(generation.actions.left_arm_action.scale, (0.02,) * 3 + (0.1,) * 3)
        self.assertNotEqual(generation.seed, evaluation.seed)

    def test_evaluation_changes_do_not_change_generation_native_config(self):
        before = resolve(self.path)
        self.cfg['evaluation']['episode_length_s'] = 7
        self.save()
        after = resolve(self.path)
        self.assertEqual(before['native'], after['native'])
        self.assertEqual(before['task_contract_hash'], after['task_contract_hash'])

    def test_reject_unknown_conflicting_and_invalid_contracts(self):
        original = copy.deepcopy(self.cfg)
        for section, key, value in [('common', 'typo', 1), ('common', 'seed', True),
                ('evaluation', 'num_envs', 3), ('evaluation', 'episode_length_s', float('nan')),
                ('evaluation', 'policy_args', {'num_steps': 12}),
                ('evaluation', 'policy_args', {'remote_kill_on_exit': True})]:
            with self.subTest(key=key, value=value):
                self.cfg = copy.deepcopy(original)
                self.cfg[section][key] = value
                self.save()
                with self.assertRaises(ValueError):
                    resolve(self.path)

    def test_reject_conflicting_native_scales_and_profile_patches(self):
        for filename, field, value in [('embodiment.json', 'action_layout', {'position_action_scale': 0.1}),
                                      ('env_profile.json', 'events', {})]:
            with self.subTest(filename=filename):
                p = self.folder / filename
                before = p.read_text()
                data = json.loads(before)
                data[field] = value
                p.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    resolve(self.path)
                p.write_text(before)

    def test_duplicate_json_keys_fail(self):
        self.path.write_text('{"schema_version":1,"schema_version":2}')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            resolve(self.path)

    def test_both_launch_plans_use_shared_adapters_and_snapshot(self):
        run = self.folder / 'run'
        # Launch planning is host-only. Supply an isolated source fixture rather
        # than depending on untracked files in a particular GPU workstation.
        source = self.folder / 'AutoData/openarm_autodata/tasks/pick_place/configs/left_env_cfg.py'
        source.parent.mkdir(parents=True)
        source.write_text('# source fixture; never imported\n')
        with patch.object(launcher, 'ROOT', self.folder), patch.object(launcher, 'EXTENSION', self.folder / 'overlay'), patch.object(
                launcher.subprocess, 'check_output', return_value='0' * 40):
            generate = launcher.plan(self.path, 'generate', run, '/gpu/python', '/tmp/source.hdf5', '/tmp/out.hdf5')
            evaluate = launcher.plan(self.path, 'evaluate', run, '/gpu/python')
        self.assertIn('shared_config.generation', generate['launch']['argv'])
        self.assertIn('shared_config.arena:CompatibleOpenArmEnvironment', evaluate['launch']['argv'])
        argv = evaluate['launch']['argv']
        subcommand = argv.index('openarm_left_pick_place')
        self.assertGreater(argv.index('--openarm_episode_length_s'), subcommand)
        self.assertLess(argv.index('--policy_type'), subcommand)
        self.assertLess(argv.index('--device'), subcommand)
        self.assertEqual(generate['task_contract_hash'], evaluate['task_contract_hash'])
        self.assertEqual(generate['effective_seed'], 1)
        self.assertEqual(evaluate['effective_seed'], 11)
        self.assertIn(str((run / 'task_descriptor.json').resolve()), generate['launch']['argv'])
        self.assertFalse(run.exists())
        self.assertFalse(any('arena-deliveries' in x for x in evaluate['launch']['argv']))
        self.assertIn('AutoData/openarm_autodata/tasks/pick_place/configs/left_env_cfg.py', generate['source_hashes'])

    def test_missing_runtime_source_rejected_before_creating_run(self):
        run = self.folder / 'run'
        with patch.object(launcher, 'ROOT', self.folder):
            with self.assertRaisesRegex(ValueError, 'Shared runtime source missing'):
                launcher.plan(self.path, 'evaluate', run, '/gpu/python')
        self.assertFalse(run.exists())


if __name__ == '__main__':
    unittest.main()
