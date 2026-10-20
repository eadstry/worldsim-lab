# AutoData HDF5 → LeRobot v3

Uses the official LeRobot 0.4.3 writer (`create`, `add_frame`, `save_episode`,
`finalize`), including v3 Parquet metadata, statistics, episode offsets and H.264
video shards. Conversion is local; no Hugging Face upload occurs.

The supplied OpenArm source contains four successful episodes. This exporter
requires the observed 7-D relative TCP action layout and uint8 HWC cameras; it
rejects inconsistent schemas and frame counts rather than guessing.

## Mapping and timing

- `action` ← `actions`: exact raw delta-position, delta-rotation and gripper command.
- `observation.state` ← `obs/joint_pos`: exact **pre-action** policy observation,
  relative to default joint positions in the archived OpenArm configuration.
- Other numeric `obs` fields retain their names under `observation.*`;
  `obs/actions` becomes `observation.last_action`.
- Three `obs/*_rgb` arrays become `observation.images.*` H.264 video, at original
  resolution and frame rate. Video compression is lossy; numeric conversion is exact.
- `states/**` becomes `next.sim_state.*`, preserving **post-action** scene state.
  Joint positions here are absolute; root positions are relative to environment origins.
- `processed_actions` becomes `processed_action` when present.
- `initial_state` and source checksum are preserved in `conversion.json`.

Episode-local `timestamp = frame_index / fps` timestamps the command and pre-action
observation. The corresponding `next.sim_state.*` is one control step later.
Source joint names are absent; `column_N` preserves column order without inventing names.

## Run

Use an isolated virtual environment rather than changing the simulation environment.
The tested environment versions are recorded inside `conversion.json` in the delivered archive.
The conversion host used Python 3.12, LeRobot 0.4.3, PyTorch 2.11,
TorchVision 0.26, TorchCodec 0.12 and PyAV 15.1. TorchCodec used the FFmpeg 7
shared libraries bundled with that PyAV wheel, through task-local linker names.
These PyTorch/TorchCodec versions exceed LeRobot 0.4.3's declared dependency
ranges; the checks below validate this specific conversion and readback only,
not the complete LeRobot installation or policy-training compatibility.

```bash
python convert.py /absolute/path/to/source.hdf5 /absolute/path/to/new-output
python convert.py /absolute/path/to/source.hdf5 /absolute/path/to/new-output --validate-only
python -m unittest discover -s workspace-overlays/autodata-lerobot-v3 -v
```

Submit resource-intensive conversion to the shared host queue described in
`docs/task-queue.md`. Keep queued code unchanged and use a new output directory.
The exporter refuses an existing output directory, including incomplete prior output.

Validation compares **every numeric value** against HDF5, verifies frame indices and
timestamps, opens the dataset through the official loader at the beginning/middle/end
of each episode, compares decoded camera samples with the source (lossy tolerance),
and decodes **every video frame** to check counts and FPS. This validates conversion
and data access, not simulation, training or robot execution.

Format reference: https://huggingface.co/docs/lerobot/v0.4.3/en/lerobot-dataset-v3

## Validation on 2026-10-20

- Shared queue task 122: three CPU integration tests passed. The fixture contains
  multiple compressed time chunks, distinct episode/camera/frame colors and a
  singleton gripper field, and checks rejection of malformed lengths and existing outputs.
- The full conversion wrote 4 episodes of lengths 1349, 1353, 1359 and 1392.
  Its initial validation exposed the official writer's scalar representation of
  shape-(1,) fields. Validation now restores only that declared singleton axis
  before exact comparison; conversion payloads required no changes.
- Shared queue task 123: full validation passed for all 5453 frames at 30 Hz.
  All numeric values matched; all three video streams decoded 5453 frames each;
  official dataset access and source-image comparisons passed at 12 episode-boundary
  and midpoint samples. Video compression remains lossy.
- `bash scripts/cloud-check.sh --allow-uninitialized` passed in the isolated
  task worktree. The upstream submodules there were intentionally uninitialized;
  no upstream pins or working-tree changes were modified.

Self-review covered pre/post-step alignment, preservation of every observed numeric
leaf and initial state, source immutability/checksum, output overwrite rejection,
bounded asynchronous image buffers, official metadata generation/finalization,
dependency provenance and the limits of lossy video checks. No unresolved
high-severity issue was found for the supplied OpenArm source. This is agent
self-review and CPU evidence, not independent reviewer approval or GPU validation.
