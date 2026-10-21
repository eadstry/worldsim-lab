import hashlib
from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np

from regression import readback


def fixture(path, success):
    with h5py.File(path, 'w') as file:
        episode = file.create_group('data/demo_0')
        episode.attrs['success'] = success
        episode.create_dataset('actions', data=np.arange(21, dtype=np.float32).reshape(3, 7),
                               chunks=(2, 7), compression='gzip')
        episode.create_dataset('initial_state/scalar', data=5)
        for camera in ('left_hand_rgb', 'right_hand_rgb', 'third_person_rgb'):
            episode.create_dataset('obs/' + camera, data=np.full((3, 480, 640, 3), 30, np.uint8),
                                   chunks=(2, 30, 80, 1), compression='gzip')
        for key, size in [('rigid_object/cube/root_pose', 7), ('rigid_object/table/root_pose', 7),
                          ('rigid_object/cube/root_velocity', 6), ('articulation/robot/joint_position', 18)]:
            episode.create_dataset('states/' + key, data=np.zeros((3, size), dtype=np.float32))


class ReadbackTests(unittest.TestCase):
    def test_reads_both_routes_and_preserves_failed_outcome_and_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'dataset.hdf5'
            fixture(output, True)
            fixture(output.with_name('dataset_failed.hdf5'), False)
            result = readback(output, 1, lambda *args: True)
        self.assertEqual([row['recorded_success'] for row in result['episodes']], [True, False])
        digest = hashlib.sha256(np.arange(21, dtype=np.float32).reshape(3, 7).tobytes()).hexdigest()
        self.assertEqual(result['episodes'][0]['dataset_hashes']['actions'], digest)

    def test_success_with_bad_terminal_or_count_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'dataset.hdf5'
            fixture(output, True)
            with self.assertRaisesRegex(ValueError, 'terminal'):
                readback(output, 1, lambda *args: False)
            with self.assertRaisesRegex(ValueError, 'counts'):
                readback(output, 0, lambda *args: True)

    def test_nonfinite_numeric_state_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'dataset.hdf5'
            fixture(output, True)
            with h5py.File(output, 'r+') as file:
                file['data/demo_0/actions'][1, 1] = np.nan
            with self.assertRaisesRegex(ValueError, 'Nonfinite'):
                readback(output, 1, lambda *args: True)


if __name__ == '__main__':
    unittest.main()
