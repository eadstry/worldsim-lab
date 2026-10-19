# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
spec=importlib.util.spec_from_file_location('produce',Path(__file__).with_name('produce.py'))
produce=importlib.util.module_from_spec(spec)
spec.loader.exec_module(produce)


class MetadataOnlyTests(unittest.TestCase):
    def fixture(self, directory, workers=0):
        (directory/'dataset.hdf5').write_bytes(b'not an HDF5 file: production-only must never decode this')
        (directory/'dataset.run.json').write_text(json.dumps(dict(status='succeeded',config=dict(num_envs=1,export_workers=workers,generation_num_trials=1,final_hold_steps=60))))
        (directory/'task.yaml').write_text('generation_policy:\n  seed: 101\n  guarantee_success: false\n  keep_failed: true\n')
        (directory/'dataset.result.json').write_text(json.dumps(dict(num_attempts=1,num_success=1,num_failures=0)))
        rows=[dict(event='episode_started',elapsed_seconds=0),dict(event='episode_finished',elapsed_seconds=2,success=True,error=None),dict(event='output_ready',elapsed_seconds=4)]
        (directory/'dataset.telemetry.jsonl').write_text('\n'.join(json.dumps(r) for r in rows)+'\n')

    def test_opaque_output_is_never_decoded_and_quality_scope_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);self.fixture(path)
            row=produce.summarize_closed(path,1,0,101,1)
            self.assertEqual(row['image_decode'],'disabled')
            self.assertEqual(row['file_hashes'],'disabled')
            self.assertEqual(row['terminal_accepted_per_minute'],15)
            self.assertIn('not performed',row['independent_file_validation'])

    def test_changed_settings_or_count_are_rejected_from_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);self.fixture(path)
            with self.assertRaises(ValueError):produce.summarize_closed(path,1,0,202,1)
            (path/'dataset.result.json').write_text(json.dumps(dict(num_attempts=2,num_success=1,num_failures=1)))
            with self.assertRaises(ValueError):produce.summarize_closed(path,1,0,101,1)

    def test_incomplete_async_export_is_not_credited(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);self.fixture(path,2)
            with self.assertRaises(ValueError):produce.summarize_closed(path,1,2,101,1)
            (path/'dataset.export.json').write_text(json.dumps(dict(status='complete')))
            self.assertEqual(produce.summarize_closed(path,1,2,101,1)['status'],'production_complete')


if __name__=='__main__':unittest.main()
