# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Host-only real HDF5 checks using extracted upstream methods, no simulator imports."""
import ast
import json
import tempfile
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace

import h5py
import numpy as np
import torch

from export_timing import export_scope, install
from monitor import summarize

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ROOT / 'AutoData/submodules/IsaacLab-Arena/submodules/IsaacLab/source/isaaclab/isaaclab/utils/datasets'


def upstream_method(file, cls, method):
    source = (DATASETS / file).read_text()
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == cls)
    node = next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == method)
    namespace = {'torch': torch, 'EpisodeData': object}
    tree = ast.parse(textwrap.dedent(ast.get_source_segment(source, node)))
    ast.increment_lineno(tree, node.lineno - 1)
    exec(compile(tree, str(DATASETS / file), 'exec'), namespace)
    return namespace[method]


class ExportTimingTest(unittest.TestCase):
    def test_actual_writer_preserves_data_and_accounts_phases(self):
        class Episode:
            pre_export = upstream_method('episode_data.py', 'EpisodeData', 'pre_export')

            def __init__(self):
                self._data = {'actions': [torch.arange(7, dtype=torch.float32) for _ in range(4)],
                              'obs': {'rgb': [torch.full((16, 16, 3), i, dtype=torch.uint8) for i in range(4)]}}
                self.data, self.seed, self.success = self._data, 7, True

            def is_empty(self):
                return False

        class Handler:
            write_episode = upstream_method('hdf5_dataset_file_handler.py', 'HDF5DatasetFileHandler', 'write_episode')

            def __init__(self, stream):
                self._hdf5_data_group = stream.create_group('data')
                self._hdf5_data_group.attrs['total'] = 0
                self._demo_count = 0
                self.stream = stream

            def _raise_if_not_initialized(self):
                pass

            def flush(self):
                self.stream.flush()

        with tempfile.TemporaryDirectory() as directory:
            rows = []
            for index in range(2):
                with h5py.File(Path(directory) / f'{index}.hdf5', 'w') as stream:
                    episode, handler = Episode(), Handler(stream)
                    if index:
                        recorder = SimpleNamespace(_episodes={0: episode}, _dataset_file_handler=handler,
                                                   _failed_episode_dataset_file_handler=None)
                        install(recorder)
                        install(recorder)  # Idempotence: no double-counting.

                    def emit(event, **values):
                        rows.append(dict(event=event, **values))

                    with export_scope(emit, episode_id=f'episode-{index}', env_id=0):
                        episode.pre_export()
                        handler.write_episode(episode)
                        handler.flush()
            with h5py.File(Path(directory) / '0.hdf5') as baseline, h5py.File(Path(directory) / '1.hdf5') as timed:
                for name in ('actions', 'obs/rgb'):
                    a, b = baseline[f'data/demo_0/{name}'], timed[f'data/demo_0/{name}']
                    np.testing.assert_array_equal(a[:], b[:])
                    self.assertEqual(a.compression, b.compression)
                    self.assertEqual(a.compression_opts, b.compression_opts)
                    self.assertEqual(a.chunks, b.chunks)
                self.assertEqual(dict(baseline['data/demo_0'].attrs), dict(timed['data/demo_0'].attrs))
                self.assertEqual(baseline['data'].attrs['total'], timed['data'].attrs['total'])
            row = rows[-1]
            self.assertEqual([r['phase'] for r in row['operations']].count('prepare_stack'), 1)
            self.assertEqual([r['phase'] for r in row['operations']].count('cpu_numpy'), 2)
            self.assertEqual([r['phase'] for r in row['operations']].count('dataset_create'), 2)
            self.assertGreaterEqual(row['other_seconds'], 0)
            self.assertAlmostEqual(sum(row['phases_seconds'].values()) + row['other_seconds'], row['duration_seconds'])
            self.assertEqual(summarize(rows)['export_breakdown']['count'], 2)
            json.dumps(rows)

    def test_failed_export_keeps_exception_and_resets_context(self):
        rows = []

        def emit(event, **values):
            rows.append(dict(event=event, **values))

        with self.assertRaisesRegex(RuntimeError, 'disk error'):
            with export_scope(emit, episode_id='failed'):
                raise RuntimeError('disk error')
        self.assertIn('disk error', rows[0]['error'])
        from export_timing import _context
        self.assertIsNone(_context.get())


if __name__ == '__main__':
    unittest.main()
