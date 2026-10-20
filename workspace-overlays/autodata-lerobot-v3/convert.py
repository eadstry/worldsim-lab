#!/usr/bin/env python3
"""Convert AutoData HDF5 to LeRobot v3 using the official writer, without Hub uploads."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
from pathlib import Path

import h5py
import numpy as np


ACTION_NAMES = ["delta_x", "delta_y", "delta_z", "delta_rx", "delta_ry", "delta_rz", "gripper"]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def leaves(group):
    result = {}
    group.visititems(lambda key, value: result.update({key: value}) if isinstance(value, h5py.Dataset) else None)
    return result


def feature_map(episode):
    """Map every time-series leaf, preserving pre/post-step semantics."""
    joint_space = "joint_actions" in episode
    result = {"action": "joint_actions" if joint_space else "actions"}
    if joint_space:
        result["source_action"] = "actions"
        result["diagnostics.applied_joint_target"] = "joint_applied_targets"
    for path in leaves(episode["obs"]):
        if path == "joint_pos_absolute" and joint_space:
            key = "observation.state"
        elif path == "joint_pos":
            key = "observation.joint_pos_relative" if joint_space else "observation.state"
        elif path == "actions":
            key = "observation.last_tcp_action" if joint_space else "observation.last_action"
        elif path.endswith("_rgb"):
            key = "observation.images." + path.removesuffix("_rgb").replace("/", ".")
        else:
            key = "observation." + path.replace("/", ".")
        result[key] = "obs/" + path
    for path in leaves(episode["states"]):
        result["next.sim_state." + path.replace("/", ".")] = "states/" + path
    if "processed_actions" in episode:
        result["source_processed_action" if joint_space else "processed_action"] = "processed_actions"
    if len(set(result.values())) != len(result):
        raise ValueError("Ambiguous feature mapping")
    return result


def load_semantics(source, metadata_path=None):
    """Prefer recorded metadata; legacy sidecars must bind to this exact HDF5."""
    env = json.loads(source['data'].attrs['env_args'])
    embedded = env.get('semantic_metadata')
    if metadata_path is not None:
        sidecar = json.loads(Path(metadata_path).read_text())
        if sidecar.get('source_sha256') != sha256(source.filename):
            raise ValueError('Semantic sidecar does not match the source HDF5 checksum')
        schema = sidecar['semantic_metadata']
        if embedded is not None and embedded != schema:
            raise ValueError('Sidecar conflicts with embedded semantic metadata')
    else:
        schema = embedded
    if not isinstance(schema, dict) or schema.get('schema_version') != 1:
        raise ValueError('Missing semantic_metadata; legacy HDF5 requires a verified --metadata sidecar')
    return schema


def inspect_source(source, semantic_metadata=None):
    """Reject inconsistent sources before creating output; never load full RGB arrays."""
    data = source["data"]
    env_args = json.loads(data.attrs["env_args"])
    semantics = load_semantics(source) if semantic_metadata is None else semantic_metadata
    sim = env_args["sim_args"]
    fps_float = 1 / (sim["dt"] * sim["decimation"])
    fps = round(fps_float)
    if not np.isclose(fps, fps_float):
        raise ValueError("LeRobot requires integer fps for this exporter")
    episodes = sorted(data, key=lambda key: int(key.removeprefix("demo_")))
    if not episodes:
        raise ValueError("Empty HDF5")
    mapping = feature_map(data[episodes[0]])
    features = {}
    lengths = []
    for name in episodes:
        ep = data[name]
        if not bool(ep.attrs.get("success", False)):
            raise ValueError(f"{name} is not a successful episode")
        if feature_map(ep) != mapping:
            raise ValueError(f"{name}: feature set differs")
        if ep["actions"].ndim != 2 or ep["actions"].shape[1] != 7:
            raise ValueError("Expected the OpenArm 7-D relative-pose action layout")
        length = len(ep["actions"])
        if not length:
            raise ValueError("Empty episode")
        lengths.append(length)
        for key, path in mapping.items():
            value = ep[path]
            if len(value) != length:
                raise ValueError(f"{name}/{path}: inconsistent frame count")
            shape = value.shape[1:]
            if key.startswith("observation.images."):
                if len(shape) != 3 or shape[-1] != 3 or value.dtype != np.uint8:
                    raise ValueError(f"{path}: expected uint8 HWC RGB")
                feature = {"dtype": "video", "shape": shape, "names": ["height", "width", "channels"]}
            else:
                if value.dtype != np.float32 or len(shape) != 1:
                    raise ValueError(f"{path}: expected float32 vector")
                if not np.isfinite(value[:]).all():
                    raise ValueError(f"{path}: non-finite values")
                spec = semantics.get('fields', {}).get(path, {})
                names = spec.get('names')
                if (not isinstance(names, list) or len(names) != shape[0]
                        or any(not isinstance(n, str) or not n or n.startswith('column_') for n in names)
                        or len(set(names)) != len(names)):
                    raise ValueError(f'{path}: missing or invalid semantic dimension names')
                if len(spec.get('units', [])) != shape[0]:
                    raise ValueError(f'{path}: missing per-dimension units')
                feature = {"dtype": "float32", "shape": shape, "names": names}
            if key in features and feature != features[key]:
                raise ValueError(f"{name}/{path}: inconsistent feature schema")
            features[key] = feature
    if mapping['action'] == 'joint_actions':
        action, state = features['action'], features['observation.state']
        if (action['names'] != state['names'] or action['shape'] != (9,)
                or state['shape'] != (9,)
                or semantics.get('joint_control', {}).get('names') != action['names']):
            raise ValueError('Joint action/state must have identical verified nine-joint names and order')
        for path in ('joint_actions', 'obs/joint_pos_absolute', 'joint_applied_targets'):
            if (semantics['fields'][path]['units'] != ['rad'] * 9
                    or semantics['fields'][path]['names'] != action['names']):
                raise ValueError('Joint action/state and applied targets must use identical names and radians')
        if semantics['fields']['joint_actions'].get('representation') != 'absolute_joint_position_target':
            raise ValueError('Joint actions must be recorded absolute controller targets')
    return episodes, lengths, fps, mapping, features, env_args


def validate(source_path, output):
    """Check exact numeric round trip, every video frame, and official random access."""
    import av
    import pyarrow.parquet as pq
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    provenance = json.loads((output / "conversion.json").read_text())
    if sha256(source_path) != provenance["source_sha256"]:
        raise ValueError("Source checksum differs from conversion source")
    table_files = sorted((output / "data").rglob("*.parquet"))
    import pyarrow as pa
    table = pa.concat_tables([pq.read_table(path) for path in table_files]).to_pandas()
    with h5py.File(source_path, "r") as source:
        semantics = provenance['semantic_metadata']
        episodes, lengths, fps, mapping, features, _ = inspect_source(source, semantics)
        info = json.loads((output / 'meta/info.json').read_text())
        for key, feature in features.items():
            if info['features'][key]['names'] != feature['names']:
                raise ValueError(f'{key}: output dimension names differ from source semantics')
        if len(table) != sum(lengths):
            raise ValueError("Output frame count differs")
        for index, (name, length) in enumerate(zip(episodes, lengths)):
            rows = table.loc[table["episode_index"] == index].sort_values("frame_index")
            np.testing.assert_array_equal(rows["frame_index"].to_numpy(), np.arange(length))
            np.testing.assert_allclose(rows["timestamp"].to_numpy(), np.arange(length) / fps, atol=1e-5, rtol=0)
            for key, path in mapping.items():
                if features[key]["dtype"] != "video":
                    actual = np.stack(rows[key])
                    # The official writer stores declared shape-(1,) features as
                    # scalar Parquet columns. Restore that singleton for comparison.
                    if features[key]["shape"] == (1,) and actual.shape == (length,):
                        actual = actual[:, None]
                    np.testing.assert_array_equal(actual, source["data"][name][path][:])
        # Official loader validates metadata offsets, video timestamps, and normalization metadata.
        ds = LeRobotDataset(provenance["repo_id"], root=output, video_backend="torchcodec")
        if ds.num_episodes != len(episodes) or len(ds) != sum(lengths):
            raise ValueError("Official loader length mismatch")
        offset = 0
        sample_count = 0
        for name, length in zip(episodes, lengths):
            for local in sorted({0, length // 2, length - 1}):
                frame = ds[offset + local]
                np.testing.assert_array_equal(frame["action"].numpy(), source["data"][name][mapping["action"]][local])
                np.testing.assert_array_equal(frame["observation.state"].numpy(), source["data"][name][mapping["observation.state"]][local])
                for key in ds.meta.video_keys:
                    image = frame[key].numpy()
                    original = source["data"][name][mapping[key]][local].astype(np.float32) / 255
                    if image.shape != (3, *original.shape[:2]) or not np.isfinite(image).all():
                        raise ValueError(f"Invalid decoded image {key}")
                    # H.264 is lossy; detect corrupt RGB, wrong episode/camera and gross misalignment.
                    mae = float(np.abs(image.transpose(1, 2, 0) - original).mean())
                    if mae > 0.08:
                        raise ValueError(f"Video/source image mismatch {name}/{local}/{key}: {mae}")
                sample_count += 1
            offset += length
        video_counts = {}
        for key in ds.meta.video_keys:
            count = 0
            for path in sorted((output / "videos" / key).rglob("*.mp4")):
                with av.open(str(path)) as container:
                    stream = container.streams.video[0]
                    if float(stream.average_rate) != fps:
                        raise ValueError("Incorrect video frame rate")
                    count += sum(1 for _ in container.decode(video=0))
            if count != sum(lengths):
                raise ValueError(f"{key}: video frame count mismatch {count}")
            video_counts[key] = count
    report = {"status": "passed", "episodes": len(episodes), "frames": sum(lengths),
              "fps": fps, "numeric_roundtrip": "all values exact", "official_loader_samples": sample_count,
              "fully_decoded_video_frames": video_counts, 'semantic_names': 'all exported feature names match source schema',
              "scope": "CPU data conversion and decoding; no simulation or training"}
    (output / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


def convert(source_path, output, repo_id, metadata_path=None):
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    source_stat = source_path.stat()
    digest = sha256(source_path)
    with h5py.File(source_path, "r") as source:
        semantics = load_semantics(source, metadata_path)
        episodes, lengths, fps, mapping, features, env_args = inspect_source(source, semantics)
        dataset = LeRobotDataset.create(repo_id=repo_id, root=output, fps=fps, features=features,
                                       robot_type="openarm_bimanual_left_ik_rel", use_videos=True,
                                       video_backend="torchcodec", vcodec="h264", image_writer_threads=2)
        initial_states = {}
        try:
            for name, length in zip(episodes, lengths):
                ep = source["data"][name]
                initial_states[name] = {path: value[:].tolist() for path, value in leaves(ep["initial_state"]).items()}
                # Numeric arrays are small. Read RGB by HDF5 time chunk to avoid
                # decompressing the same multi-frame gzip chunks for every frame.
                numeric = {key: ep[path][:] for key, path in mapping.items() if features[key]["dtype"] != "video"}
                cameras = {key: ep[path] for key, path in mapping.items() if features[key]["dtype"] == "video"}
                frame_bytes = sum(int(np.prod(value.shape[1:])) * value.dtype.itemsize for value in cameras.values())
                memory_limit_frames = max(1, 256 * 1024 * 1024 // max(1, frame_bytes))
                block_frames = min(memory_limit_frames, 128, max(
                    (value.chunks[0] if value.chunks else 32 for value in cameras.values()), default=32))
                for start in range(0, length, block_frames):
                    end = min(start + block_frames, length)
                    images = {key: value[start:end] for key, value in cameras.items()}
                    for i in range(start, end):
                        frame = {key: value[i].copy() for key, value in numeric.items()}
                        frame.update({key: value[i - start] for key, value in images.items()})
                        frame["task"] = "Pick up the cube with the left arm and place it at the target."
                        dataset.add_frame(frame)
                    # Bound asynchronous image buffers to this block's memory budget.
                    dataset.image_writer.wait_until_done()
                dataset.save_episode(parallel_encoding=False)
                print(f"Saved {name}: {length} frames", flush=True)
        finally:
            dataset.stop_image_writer()
            dataset.finalize()
        if (source_path.stat().st_size, source_path.stat().st_mtime_ns) != (source_stat.st_size, source_stat.st_mtime_ns):
            raise RuntimeError("Source changed during conversion")
        provenance = {"source": str(source_path), "source_sha256": digest, "repo_id": repo_id,
                      "lerobot_version": importlib.metadata.version("lerobot"), "format_version": "v3.0",
                      "runtime_versions": {name: importlib.metadata.version(name) for name in
                                           ["lerobot", "datasets", "av", "torch", "torchvision", "torchcodec",
                                            "numpy", "h5py", "pyarrow", "accelerate", "draccus"]},
                      "python_version": platform.python_version(),
                      "source_env_args": env_args, "episodes": episodes, "lengths": lengths,
                      'semantic_metadata': semantics,
                      "feature_mapping": mapping, "initial_states": initial_states,
                      "semantics": {"observation.state": ("Active-arm absolute pre-step joint angles in radians" if mapping["action"] == "joint_actions" else "Exact pre-step obs/joint_pos, relative to default joint positions"),
                                    "action": ("Recorded absolute controller joint targets in radians; rate-limited internally, not measured next-state angles" if mapping["action"] == "joint_actions" else "Exact raw 7-D relative end-effector pose plus binary gripper command"),
                                    "next.sim_state.*": "Exact post-step simulation states, absolute joint positions, root positions relative to environment origins",
                                    "timestamp": "Episode-local command/observation time, frame_index / fps; post-step simulation states are one control interval later",
                                    "video": "Three RGB streams encoded as lossy H.264 yuv420p at original size and rate",
                                    "joint_names": "Dimension names use recorded metadata or a checksum-bound historical recovery sidecar"}}
        (output / "conversion.json").write_text(json.dumps(provenance, indent=2) + "\n")
        (output / "README.md").write_text(
            "# AutoData OpenArm — LeRobot v3.0\n\n"
            f"{len(episodes)} successful episodes, {sum(lengths)} frames, {fps} Hz.\n\n" +
            ("`action` and `observation.state`: same nine active-arm joint names/order, radians; target vs measured pre-step angle.\n"
             "Original TCP actions retained as `source_action`; final ramped targets as `diagnostics.applied_joint_target`.\n"
             if mapping["action"] == "joint_actions" else
             "`action`: raw 7-D TCP command; `observation.state`: 18-D relative pre-step joint observation.\n") +
            "`next.sim_state.*`: post-action full scene state, including absolute joint positions.\n"
            "Other numeric observations, processed actions and three RGB cameras are preserved.\n"
            "Video is lossy H.264; numeric data is exact. No simulation, policy training or Hub upload was performed.\n\n"
            "Read conversion.json for source checksum, field mapping, timing and initial states.\n\n"
            "```python\nfrom lerobot.datasets.lerobot_dataset import LeRobotDataset\n"
            f"ds = LeRobotDataset('{repo_id}', root='/absolute/path/to/openarm-left-lerobot-v3')\n"
            "sample = ds[0]\n```\n"
        )
    validate(source_path, output)


def rename_existing(source_path, previous, output, metadata_path):
    """Create a new named version without recompressing or changing any numeric/video payload."""
    if output.exists():
        raise FileExistsError(output)
    if metadata_path is None:
        raise ValueError('Historical renaming requires a checksum-bound --metadata sidecar')
    with h5py.File(source_path, 'r') as source:
        semantics = load_semantics(source, metadata_path)
        _, _, _, mapping, features, _ = inspect_source(source, semantics)
    old_provenance = json.loads((previous / 'conversion.json').read_text())
    if old_provenance['source_sha256'] != sha256(source_path) or old_provenance['feature_mapping'] != mapping:
        raise ValueError('Existing LeRobot dataset does not match the source')
    info = json.loads((previous / 'meta/info.json').read_text())
    for key, feature in features.items():
        old = info['features'][key]
        if tuple(old['shape']) != tuple(feature['shape']) or old['dtype'] != feature['dtype']:
            raise ValueError(f'{key}: schema cannot be changed by renaming')
        old['names'] = feature['names']
    shutil.copytree(previous, output)
    for stale in ('validation.json', 'delivery-manifest.json'):
        (output / stale).unlink(missing_ok=True)
    (output / 'meta/info.json').write_text(json.dumps(info, indent=4) + '\n')
    old_provenance['semantic_metadata'] = semantics
    old_provenance['semantics']['joint_names'] = 'Recovered from archived runtime evidence; see semantic_metadata.evidence'
    old_provenance['renamed_from'] = str(previous)
    (output / 'conversion.json').write_text(json.dumps(old_provenance, indent=2) + '\n')
    with (output / 'README.md').open('a') as stream:
        stream.write('\nSemantic names restored in a new version from checksum-bound historical evidence.\n'
                     'See conversion.json for joint order, units, coordinate frames, action scales and recovery provenance.\n')
    validate(source_path, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repo-id", default="local/autodata-openarm-left")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument('--metadata', type=Path, help='Checksum-bound semantic sidecar for historical HDF5')
    parser.add_argument('--rename-from', type=Path, help='Create a new named version of an existing conversion')
    parser.add_argument("--require-joint-space", action="store_true", help="Reject sources without recorded joint targets")
    args = parser.parse_args()
    if args.require_joint_space:
        with h5py.File(args.source, "r") as source:
            _, _, _, mapping, _, _ = inspect_source(source)
            if mapping["action"] != "joint_actions":
                raise ValueError("Source lacks recorded joint targets; regenerate instead of relabeling TCP actions")
    # Local caches only; never contact or publish to the Hub when reading output.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    if args.rename_from:
        rename_existing(args.source.resolve(), args.rename_from.resolve(), args.output.resolve(), args.metadata)
    elif args.validate_only:
        validate(args.source.resolve(), args.output.resolve())
    else:
        convert(args.source.resolve(), args.output.resolve(), args.repo_id, args.metadata)


if __name__ == "__main__":
    main()
