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
Numeric dimension names and units must be supplied by `env_args.semantic_metadata`.
The converter rejects missing names, `column_N` placeholders, conflicting schemas,
and sidecars whose source checksum does not match. It never assumes URDF declaration
order equals the articulation's runtime order.

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

For a historical HDF5 lacking metadata, pass a verified `--metadata /path/to/sidecar.json`.
The sidecar contains `source_sha256` and `semantic_metadata`. To create a new named
version without modifying Parquet/MP4 payloads or the previous delivery:

```bash
python convert.py source.hdf5 new-output --metadata verified.json --rename-from previous-output
```

`recover_legacy_metadata.py` supports this specific OpenArm source. It reads indexed
runtime joint tables, checks the supplied URDF's joint types, verifies every source
frame's default offsets/gripper column/action scale, and can compare labels with a
fresh GPU metadata smoke report. Evidence and checksums remain in the sidecar;
historical recovery is explicitly distinguished from original runtime capture.

The local production launcher captures metadata automatically. The accompanying
`AutoData-openarm-semantic-metadata.patch` offers the equivalent OpenArm-only hook
for direct use of the upstream generation script. It is provided for review and is
not automatically applied to upstream. That hook requires
`workspace-overlays/openarm-production` on `PYTHONPATH`; its `attach()` is idempotent.

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

## Semantic metadata repair

The original delivery checked numeric preservation but left dimension-name
placeholders. The repair adds strict name/unit checks and a naming-only migration.
Five conversion tests cover semantic names, singleton fields, exact numeric/video
payload preservation, incomplete/conflicting runtime tables, missing metadata,
wrong-source sidecars and refusal to overwrite outputs.

The OpenArm producer's 36 host tests passed, including native joint-order capture,
resolved observation subsets, processed gripper order, mutation isolation and
real synchronous HDF5/async spawn persistence. Tests that extract upstream methods
accept `WORLDSIM_SOURCE_ROOT` as a read-only fixture source in isolated worktrees.

Shared queue task 124 passed a real one-environment GPU smoke: environment creation,
three zero-action steps, synchronous HDF5 export and metadata readback. Its live joint
order and 28 field label sets match the historical recovery; joint default offsets
also match. This does not validate task success, full generation or training.

Shared queue task 125 verified the named v002 delivery: 5453 frames, every numeric
value exact, 5453 decoded frames per camera, 12 official-loader samples, and all
exported semantic names matching the verified recovery schema. The previous
delivery and original HDF5 were preserved. The v002 archive additionally includes
the recovery sidecar and GPU smoke metadata report.
