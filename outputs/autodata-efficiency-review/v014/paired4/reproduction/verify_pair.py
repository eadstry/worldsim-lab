# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Read-only paired dataset metadata/action checks after both GPU runs exit."""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import h5py
import numpy as np


def inventory(path):
    records = []
    with h5py.File(path, "r") as file:
        for name, episode in file["data"].items():
            actions = np.asarray(episode["actions"])
            rgb = {}
            for channel in ("left_hand_rgb", "right_hand_rgb", "third_person_rgb"):
                dataset = episode[f"obs/{channel}"]
                rgb[channel] = {"shape": list(dataset.shape), "dtype": str(dataset.dtype),
                                "compression": dataset.compression,
                                "compression_opts": dataset.compression_opts}
                assert dataset.shape == (len(actions), 480, 640, 3)
                assert dataset.dtype == np.uint8 and dataset.compression == "gzip" and dataset.compression_opts == 2
            records.append({"episode": name, "action_shape": list(actions.shape),
                            "action_sha256": hashlib.sha256(actions.tobytes()).hexdigest(), "rgb": rgb})
    return records


def verify(directory):
    for variant in ("before_sync", "after_auto"):
        run = json.loads((directory / variant / "episodes.run.json").read_text())
        assert run["status"] == "succeeded"
    before = inventory(directory / "before_sync/episodes.hdf5")
    after = inventory(directory / "after_auto/episodes.hdf5")
    a = Counter((tuple(r["action_shape"]), r["action_sha256"]) for r in before)
    b = Counter((tuple(r["action_shape"]), r["action_sha256"]) for r in after)
    result = {"rgb_metadata_passed": True, "before": before, "after": after,
              "exact_action_sequence_matches": sum((a & b).values()),
              "all_action_sequences_match_as_multiset": a == b,
              "scope": "Full action arrays and RGB metadata; image pixels are not compared"}
    (directory / "pair-data-check.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({k:v for k,v in result.items() if k not in ('before','after')}))


if __name__ == "__main__":
    verify(Path(sys.argv[1]).resolve())
