"""CPU-only integration checks for timing, round trips and malformed input."""

import json
import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

from convert import convert, inspect_source, load_semantics, rename_existing, sha256
from recover_legacy_metadata import joint_table


def fixture(path, malformed=False):
    with h5py.File(path, "w") as f:
        data = f.create_group("data")
        joint_names = [f'test_joint_{j}' for j in range(18)]
        semantic_fields = {
            'actions': {'names': ['dx', 'dy', 'dz', 'drx', 'dry', 'drz', 'gripper'], 'units': ['1'] * 7},
            'obs/joint_pos': {'names': joint_names, 'units': ['rad'] * 18},
            'obs/left_gripper_pos': {'names': ['left_finger_joint'], 'units': ['rad']},
            'states/articulation/robot/joint_position': {'names': joint_names, 'units': ['rad'] * 18},
        }
        data.attrs["env_args"] = json.dumps({"sim_args": {"dt": 1 / 120, "decimation": 4},
                                             'semantic_metadata': {'schema_version': 1, 'fields': semantic_fields}})
        for i, count in enumerate([6, 8]):
            ep = data.create_group(f"demo_{i}")
            ep.attrs["success"] = True
            ep.create_dataset("actions", data=np.full((count, 7), i + 0.2, dtype=np.float32))
            ep.create_dataset("obs/joint_pos", data=np.arange(count * 18, dtype=np.float32).reshape(count, 18) / 100)
            ep.create_dataset("obs/left_gripper_pos", data=np.arange(count, dtype=np.float32).reshape(count, 1) / 10)
            ep.create_dataset("states/articulation/robot/joint_position", data=np.full((count, 18), i + 2, dtype=np.float32))
            ep.create_dataset("initial_state/articulation/robot/joint_position", data=np.zeros((1, 18), dtype=np.float32))
            for camera_index, camera in enumerate(["left_hand", "right_hand", "third_person"]):
                length = count - 1 if malformed else count
                images = np.empty((length, 32, 32, 3), dtype=np.uint8)
                for frame in range(length):
                    images[frame] = 60 + i * 80 + camera_index * 10 + frame * 3
                ep.create_dataset(f"obs/{camera}_rgb", data=images, chunks=(3, 8, 8, 3), compression="gzip")


class ConversionTests(unittest.TestCase):
    def test_runtime_joint_table_must_be_complete_and_unambiguous(self):
        rows = [f'| {i} | openarm_test_joint{i} | 0 |' for i in range(18)]
        self.assertEqual(joint_table('\n'.join(reversed(rows))), [f'openarm_test_joint{i}' for i in range(18)])
        with self.assertRaisesRegex(ValueError, 'complete'):
            joint_table('\n'.join(rows[:-1]))
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            joint_table('\n'.join(rows + ['| 0 | openarm_wrong_joint | 0 |']))

    def test_official_roundtrip_preserves_pre_and_post_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture(root / "source.hdf5")
            convert(root / "source.hdf5", root / "converted", "local/converter-test")
            report = json.loads((root / "converted/validation.json").read_text())
            self.assertEqual(report["frames"], 14)
            self.assertEqual(report["official_loader_samples"], 6)
            self.assertTrue(all(count == 14 for count in report["fully_decoded_video_frames"].values()))
            provenance = json.loads((root / "converted/conversion.json").read_text())
            info = json.loads((root / 'converted/meta/info.json').read_text())
            self.assertEqual(info['features']['observation.state']['names'], [f'test_joint_{j}' for j in range(18)])
            self.assertEqual(info['features']['observation.left_gripper_pos']['names'], ['left_finger_joint'])
            self.assertEqual(provenance["feature_mapping"]["observation.state"], "obs/joint_pos")
            self.assertEqual(provenance["feature_mapping"]["next.sim_state.articulation.robot.joint_position"],
                             "states/articulation/robot/joint_position")
            # Naming-only repair must leave every Parquet value and MP4 byte intact.
            schema = provenance['semantic_metadata']
            sidecar = root / 'semantic.json'
            sidecar.write_text(json.dumps({'source_sha256': sha256(root / 'source.hdf5'), 'semantic_metadata': schema}))
            old_info = json.loads((root / 'converted/meta/info.json').read_text())
            old_info['features']['observation.state']['names'] = [f'column_{j}' for j in range(18)]
            (root / 'converted/meta/info.json').write_text(json.dumps(old_info))
            rename_existing(root / 'source.hdf5', root / 'converted', root / 'renamed', sidecar)
            renamed_info = json.loads((root / 'renamed/meta/info.json').read_text())
            self.assertEqual(renamed_info['features']['observation.state']['names'], [f'test_joint_{j}' for j in range(18)])
            self.assertEqual(json.loads((root / 'converted/meta/info.json').read_text())['features']['observation.state']['names'][0], 'column_0')
            for p in (root / 'converted').rglob('*'):
                if p.suffix in ('.parquet', '.mp4'):
                    self.assertEqual(sha256(p), sha256(root / 'renamed' / p.relative_to(root / 'converted')))

    def test_missing_placeholder_or_wrong_source_metadata_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture(root / 'source.hdf5')
            with h5py.File(root / 'source.hdf5', 'r+') as f:
                env = json.loads(f['data'].attrs['env_args'])
                schema = env.pop('semantic_metadata')
                f['data'].attrs['env_args'] = json.dumps(env)
                with self.assertRaisesRegex(ValueError, 'Missing semantic_metadata'):
                    inspect_source(f)
                schema['fields']['obs/joint_pos']['names'][0] = 'column_0'
                with self.assertRaisesRegex(ValueError, 'semantic dimension names'):
                    inspect_source(f, schema)
            bad = root / 'bad.json'
            bad.write_text(json.dumps({'source_sha256': 'wrong', 'semantic_metadata': schema}))
            with h5py.File(root / 'source.hdf5', 'r') as f:
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    load_semantics(f, bad)

    def test_inconsistent_camera_lengths_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.hdf5"
            fixture(path, malformed=True)
            with h5py.File(path, "r") as source:
                with self.assertRaisesRegex(ValueError, "inconsistent frame count"):
                    inspect_source(source)

    def test_source_not_modified_and_existing_output_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture(root / "source.hdf5")
            before = (root / "source.hdf5").read_bytes()
            (root / "existing").mkdir()
            with self.assertRaises(FileExistsError):
                convert(root / "source.hdf5", root / "existing", "local/converter-test")
            self.assertEqual(before, (root / "source.hdf5").read_bytes())


if __name__ == "__main__":
    unittest.main()
