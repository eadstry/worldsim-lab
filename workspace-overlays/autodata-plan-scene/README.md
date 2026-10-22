# Actual scene, plan and execution comparison

This probe runs the prepared OpenArm left-arm AutoData SkillGen pipeline with
cuRobo on the existing GPU runtime. It uses one source episode and seed 101 in
three scenarios: default cube position, XY offsets (-35, +50) mm, and (+35, -50)
mm. These lie within the task's original ±40/±60 mm range. The events use fixed
in-range samples to isolate scene effects from random draw differences.

The original three dataset cameras and success thresholds remain configured as
before. A separate diagnostic camera and non-colliding USD curves capture the
predicted transit paths (orange), generated skill reference paths (blue) and measured TCP
history (green). Rendering overhead means these runs are not throughput benchmarks.
One attempted episode per scenario does not estimate success rates.

Submit each case to the shared host queue, supplying the existing prepared workspace:

```bash
python3 scripts/task-queue.py submit --name scene-baseline --timeout 1800 -- \
  bash workspace-overlays/autodata-plan-scene/run.sh \
  --workspace /home/tangyuan/WorldSimReady-Home \
  --directory runs/autodata-plan-scene-NEW/baseline --case baseline
```

Repeat with `--case offset-a` / `offset-b` and independent corresponding output
directories. Do not edit the submitted launcher/hook code while any case is queued
or running. This task worktree intentionally uses the original prepared runtime
through an explicit workspace argument; it does not initialize or change upstream
submodules or install dependencies. Each run records source SHA256 values.

After all cases complete, queue the existing production `validate_output.py` on
each `episodes.hdf5`. Its recorded success and strict placement/release/velocity
checks are retained even if they fail. Then use the existing autodata Python:

```bash
python workspace-overlays/autodata-plan-scene/recover_capture.py runs/autodata-plan-scene-NEW
python workspace-overlays/autodata-plan-scene/package.py \
  --run-root runs/autodata-plan-scene-NEW \
  --output outputs/autodata-plan-scene/vNEW --widget /absolute/writable/path/actual-plan-scene.html
python workspace-overlays/autodata-plan-scene/test_recover_capture.py
```

Isaac Sim can terminate the Python process before the outer launcher's `finally`
executes. The planner snapshots therefore contain only the first portion of the
frame metadata. `recover_capture.py` crosschecks every persisted live TCP and cube
state with independently recorded HDF5 observations/states to 1e-6 m, verifies the
exact frame-file sequence and count, and recovers later frame metadata from those
same HDF5 streams. It preserves the original snapshot and writes a separate
`probe-recovered.json`. Source stability is checked after the run. Tests reject
shifted observations and missing frames. Generated skill curves stay in the scene as retained references. The partial
numeric snapshot includes only the first skill segment; rendered blue curves
include the skill references generated at each frame, and the complete measured
TCP trajectory comes from HDF5.

Each inline view contains downsampled real frames with no image interpolation,
aligned by simulation time. Full JPEG captures, raw HDF5 datasets and telemetry
stay in ignored run directories. The output snapshot includes representative
frames, all plan/TCP arrays, checks and source hashes. No training or sim-to-real
claim is made; the historical source annotations were inferred from a replay
fixture and have not been human reviewed.
