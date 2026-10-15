# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Host checks for terminal acceptance and fail-closed source integration."""
import unittest

from terminal_gate import guarded_source, terminal_success


class GateTests(unittest.TestCase):
    def test_source_gate_precedes_success_flag_and_export(self):
        source = '''async def generate():
    env = self.datastream.get_env()
    env.recorder_manager.set_success_to_episodes(ids, flags)
    env.recorder_manager.export_episodes(ids)
'''
        updated = guarded_source(source)
        compile(updated, '<test>', 'exec')
        self.assertLess(updated.index('buffers.success ='), updated.index('set_success_to_episodes'))
        with self.assertRaises(ValueError):
            guarded_source(source.replace('set_success_to_episodes', 'changed_method'))

    def test_accept_rest_and_reject_moving_or_off_pad(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest('Numerical checks use the existing configured runtime NumPy')
        cube = np.array([.35, .19, .5395, 0., 0., 0., 1.])
        table = np.array([0., 0., 0., 0., 0., 0., 1.])
        joints = np.zeros(18)
        joints[14] = .7
        self.assertTrue(terminal_success(cube, table, np.zeros(6), joints))
        self.assertFalse(terminal_success(cube, table, np.array([.21, 0, 0, 0, 0, 5.7]), joints))
        cube[0] = .1
        self.assertFalse(terminal_success(cube, table, np.zeros(6), joints))


if __name__ == '__main__':
    unittest.main()
