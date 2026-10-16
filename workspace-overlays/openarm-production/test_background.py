# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Host checks for batch isolation, invalid assets and exported provenance."""
import json
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from background import select_background, configure_background, annotate_dataset
from generate import build_source


class BackgroundTest(unittest.TestCase):
    def test_pool_validation_and_independent_rng(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('a', 'b'):
                (root / f'{name}.hdr').write_bytes(name.encode())
            config = root / 'pool.json'
            config.write_text(json.dumps({'candidates': [dict(name=n, path=f'{n}.hdr') for n in ('a', 'b')]}))
            state = random.getstate()
            a = select_background(config, 101)
            self.assertEqual(a, select_background(config, 101))
            self.assertEqual(state, random.getstate())
            self.assertEqual(a['selected']['path'], str(root / 'a.hdr'))
            cfg = SimpleNamespace(scene=SimpleNamespace(dome_light=SimpleNamespace(spawn=SimpleNamespace()), ground=SimpleNamespace(spawn=SimpleNamespace())))
            configure_background(cfg, a)
            self.assertTrue(cfg.wait_for_textures)
            self.assertEqual(cfg.scene.dome_light.spawn.texture_file, a['selected']['path'])
            (root / 'b.hdr').unlink()
            with self.assertRaises(ValueError):
                select_background(config, 101)  # Validate even unselected candidates.

    def test_export_provenance_and_changed_texture(self):
        import h5py
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'a.hdr').write_bytes(b'texture')
            config = root / 'pool.json'
            config.write_text(json.dumps({'candidates': [dict(name='a', path='a.hdr')]}))
            record = select_background(config, 4)
            output = root / 'data.hdf5'
            output.with_suffix('.background.json').write_text(json.dumps(record))
            with h5py.File(output, 'w') as f:
                f.create_group('data/demo_0')
            annotate_dataset(output)
            with h5py.File(output) as f:
                self.assertEqual(json.loads(f['data/demo_0'].attrs['background'])['selected']['name'], 'a')
            (root / 'a.hdr').write_bytes(b'changed')
            with self.assertRaises(AssertionError):
                annotate_dataset(output)

    def test_hook_order_and_fail_closed(self):
        source = '''simulation_app = app_launcher.app
if True:
    generation_policy_params = task_descriptor.get_generation_policy()
    env = gym.make(env_name, cfg=env_cfg).unwrapped
    if True:
        stats["num_attempts"] += 1
        env.close()
    simulation_app.close()
'''
        args = SimpleNamespace(debug_planner=False, final_hold_steps=60, generation_num_trials=1,
                               num_envs=1, background={'selected': {'name': 'a'}},
                               output_file=Path('/tmp/unused-background.hdf5'), export_workers=0)
        patched = build_source(source, args)
        compile(patched, '<test>', 'exec')
        self.assertLess(patched.index('configure_background(env_cfg'), patched.index('env = gym.make'))
        self.assertLess(patched.index('env.close()'), patched.index('annotate_dataset('))
        self.assertLess(patched.index('annotate_dataset('), patched.index('simulation_app.close()'))
        with self.assertRaises(AssertionError):
            build_source(source.replace('    env = gym.make(env_name, cfg=env_cfg).unwrapped', ''), args)


if __name__ == '__main__':
    unittest.main()
