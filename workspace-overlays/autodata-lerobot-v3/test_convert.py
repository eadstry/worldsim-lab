"""CPU-only integration checks for timing, round trips and malformed input."""

import json
import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

from convert import convert, inspect_source


def fixture(path, malformed=False):
    with h5py.File(path, "w") as f:
        data = f.create_group("data")
        data.attrs["env_args"] = json.dumps({"sim_args": {"dt": 1 / 120, "decimation": 4}})
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
            self.assertEqual(provenance["feature_mapping"]["observation.state"], "obs/joint_pos")
            self.assertEqual(provenance["feature_mapping"]["next.sim_state.articulation.robot.joint_position"],
                             "states/articulation/robot/joint_position")

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
