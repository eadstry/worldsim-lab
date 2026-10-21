import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from audit import image_metrics, journal_runs


class AuditTests(unittest.TestCase):
    def test_initial_black_frames_do_not_count_as_persistent_blackout(self):
        frames = np.full((40, 4, 4, 3), 100, dtype=np.uint8)
        frames[:30] = 0
        report = image_metrics(frames, chunk=7)
        self.assertEqual(report['suspected_black_frames'], 30)
        self.assertEqual(report['post_warmup_suspected_black_fraction'], 0)

    def test_near_black_stream_and_empty_post_warmup(self):
        frames = np.zeros((4, 4, 4, 3), dtype=np.uint8)
        frames[:, 0, 0, 0] = 2
        report = image_metrics(frames)
        self.assertEqual(report['suspected_black_fraction'], 1)
        self.assertIsNone(report['post_warmup_suspected_black_fraction'])

    def test_rejects_wrong_shape_empty_and_float_frames(self):
        for frames in (np.empty((0, 4, 4, 3), np.uint8), np.zeros((4, 4, 3), np.uint8),
                       np.zeros((4, 4, 4, 3), np.float32)):
            with self.assertRaises(ValueError):
                image_metrics(frames)

    def test_interleaved_runs_remain_separate_and_malformed_line_is_counted(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'events.jsonl'
            rows = [dict(run_id='a', event='start', time_utc='2026-10-20T00:00:00Z'),
                    dict(run_id='b', event='start', time_utc='2026-10-20T00:00:01Z'),
                    dict(run_id='a', event='finish', time_utc='2026-10-20T00:00:02Z')]
            path.write_text('\n'.join(map(json.dumps, rows)) + '\ninvalid\n')
            report = journal_runs(path)
        self.assertEqual(report['invalid_lines'], 1)
        self.assertEqual(report['runs']['a']['events'], {'start': 1, 'finish': 1})
        self.assertEqual(report['runs']['b']['events'], {'start': 1})


if __name__ == '__main__':
    unittest.main()
