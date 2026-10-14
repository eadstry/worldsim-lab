# OpenArm AutoData local production overlay

The supplied ZIP is used for robot/task assets and original SkillGen YAMLs. This overlay
adapts them to the recorded AutoData checkout without changing upstream source or the
installed conda environment. Use the local `autodata` Python; Docker is not required.

## Evidence and scope

2026-10-14 update: the later eight-environment run targeting 100 successful episodes
ended with SIGKILL after telemetry recorded 49 successes and 6 failures, with 8
episodes unfinished. These counts have not been independently checked by reading
the final HDF5. Monitoring has therefore been exercised in a real run, including
abnormal child termination; full-target production acceptance remains outstanding.
See [the process record](../../docs/process-log.md) for evidence and follow-up work.

A fresh local run generated one successful left-arm episode in one attempt. The HDF5
contains 1432 control steps, seven-dimensional actions and three 640x480 uint8 RGB
streams. Independent checks of the recorded final state pass the original placement,
release and velocity thresholds. See `runtime/left-verified-1.result.json` and
`runtime/left-verified-1.validation.json`. A four-environment run also completed with 4/4 successes; each exported final state
passes the same checks. Full results and environment versions are recorded in
`local-runtime-validation.json`. The 4 exported episodes have 1349, 1353, 1359 and
1392 steps. These five successful test episodes do not estimate a broad success rate.

The source was found in an ignored local development directory, not inside the ZIP.
`runtime/inputs/openarm_left_fixture_clearance_source.hdf5` is an unchanged copy of
that source. Its annotations were inferred from a replay fixture, not human reviewed;
see `source-provenance.json`. This verifies the production pipeline on this source,
not its annotation quality or a broad task distribution. Right-arm source data has
not been found, so no right-arm generation success is claimed. The passive right
wrist camera can be black in this left-arm task; image structure validation does
not mean every view is informative.

## Run locally

From the repository root, reproduce one successful demonstration using the provided
local source and the original left-arm task's success-target policy:

```bash
cd /home/tangyuan/WorldSimReady-Home
bash workspace-overlays/openarm-production/run-local.sh \
  --arm left --final-hold-steps 60 \
  --input_file workspace-overlays/openarm-production/runtime/inputs/openarm_left_fixture_clearance_source.hdf5 \
  --output_file ./AutoData/datasets/openarm_left_smoke.hdf5 \
  --num_envs 1 --generation_num_trials 1
```

For production using the same source:

```bash
bash workspace-overlays/openarm-production/run-local.sh \
  --arm left --final-hold-steps 60 \
  --input_file workspace-overlays/openarm-production/runtime/inputs/openarm_left_fixture_clearance_source.hdf5 \
  --output_file ./AutoData/datasets/openarm_left_num_envs_4.hdf5 \
  --num_envs 4 --generation_num_trials 100
```

All output paths must be new. With the original task YAML, `guarantee_success: true`
means the requested count is successful demonstrations; the process aborts after
25 failures. Parallel completion can exceed the requested count. The final hold adds
60 control steps (2 seconds at 30 Hz), keeping the final target and release command
while the object settles. Success thresholds are unchanged. No 100-episode benchmark
has been performed. The successful single episode is about 483 MiB with RGB;
100 similar episodes would occupy roughly 47 GiB, with variation from image compression.

The launcher sets the existing CUDA 13 package's library/toolkit paths for this
process only. Prior local EULA acceptance is documented in the preserved OpenArm
workflow. `OPENARM_PYTHON` selects a different configured Python;
`--autodata-root` selects another compatible checkout. YAML/profile/environment
selection is automatic from `--arm`. For right-arm generation, provide an actual
right-arm annotated HDF5; the left-arm source is rejected by preflight checks.

## Saved production logs and monitoring

Every new run automatically saves these files beside the output HDF5. Use a new
output name; existing datasets and log files are rejected instead of overwritten.
`--log-interval 10` controls the parent resource sampler and child heartbeat period.

| File suffix | Contents |
| --- | --- |
| `.console.log` | Complete child stdout/stderr, including startup warnings and Python tracebacks |
| `.run.json` | Run ID, exact command, requested environment count/target, PID, start/end UTC times, exit code/signal and final completion report |
| `.telemetry.jsonl` | Append-only episode starts/outcomes/cancellations, reset and export boundaries, motion planning, every cuRobo outer solve iteration, execution progress every 100 steps and periodic heartbeats |
| `.resources.jsonl` | Independent parent-side CPU/RSS/peak RSS/swap/I/O samples, output file growth, available system RAM, cgroup memory limits/events and GPU samples |
| `.telemetry-summary.json` | Child snapshot refreshed periodically and after episode completion |
| `.status.json` | Parent snapshot combining progress, resource samples, rate distributions, last activity and completion status |
| `.result.json` / `.error.txt` | Existing generator completion report / exception traceback, when produced |

For example, for an output named `openarm_left_monitored.hdf5`:

```bash
python workspace-overlays/openarm-production/monitor.py \
  --output-file AutoData/datasets/openarm_left_monitored.hdf5 --watch

# Full analysis as JSON (also available in the periodically saved .status.json):
python workspace-overlays/openarm-production/monitor.py \
  --output-file AutoData/datasets/openarm_left_monitored.hdf5 --json

tail -F AutoData/datasets/openarm_left_monitored.console.log
```

The compact monitor prints completed successes/attempts, in-flight episodes,
production speed, solver iterations/success rate, RSS and telemetry age. It does
not open the live HDF5. Both local and Docker launchers use the supervisor.

Statistics distinguish episode success, planning-phase success, and actual cuRobo
outer solver iterations. Each iteration can run multiple IK/trajectory-optimization
seeds; those seeds are not counted as independent episode attempts. Individual
iteration logs retain solver status and cuRobo-reported IK/graph/trajopt timing when
available. Cancellations during parallel shutdown are counted separately and
excluded from the completed-episode success denominator. Interrupted in-flight
episodes have unknown outcomes, not automatically failed outcomes.

Time and efficiency summaries include episode and solver mean/p50/p95/max,
reset/motion-plan/execution-wait/export durations, solver iterations per episode,
simulation steps and simulated seconds per wall second, cumulative and last-minute
successful episodes/minute, amortized wall seconds per successful episode and ETA.
ETA is absent before the first completion. Parent wall time includes application
startup; child generation rates begin at the first episode start. Episode wall time
includes reset and export. Async execution time includes queue waits shared with
other environments; summing concurrent episode times does not give total run time.
Stage timings use host wall clocks without adding CUDA synchronization; cuRobo's
reported solver times are stored separately. File growth measures bytes written,
not verified successful episodes. Recorder export calls indicate completion of that
API call; the final dataset can be checked independently below.

The parent continues sampling if the child blocks or dies and records a child
`SIGKILL` even when no Python traceback or child summary is written. A signal alone
does not prove OOM: cgroup memory event deltas provide additional evidence, and
those counters can include other processes sharing the cgroup. If the supervisor
itself is killed, its final status cannot be written; timestamps expose stale
snapshots. GPU samples use bounded `nvidia-smi` queries when available and describe
whole-device use, not this process alone. Missing GPU/cgroup access is represented
as unavailable rather than zero usage. The later eight-environment run exercised
monitoring and abnormal termination; it did not complete its 100-success target.
Host-only supervisor/instrumentation checks alone do not establish GPU runtime correctness.

Check an exported output independently:

```bash
/home/tangyuan/miniconda3/envs/autodata/bin/python \
  workspace-overlays/openarm-production/validate_output.py \
  ./AutoData/datasets/openarm_left_smoke.hdf5
```

### Export phase diagnostics

New generation processes automatically emit `export_breakdown` records and
`[OpenArm export]` console lines. Already-running processes do not reload these
hooks. The records include wall/current-thread CPU seconds for `prepare_stack`,
`cpu_numpy`, each `dataset_create` (path, raw bytes, shape and compression), and
`flush`. `write_episode_inclusive` is nested: do not add it to the exclusive
phase totals. `other_seconds` includes metadata, buffer reset and instrumentation
overhead. `monitor.py --json` exposes distributions under `export_breakdown`.

`dataset_create` combines compression, HDF5 and I/O; it is NOT pure disk time.
HDF5 `flush` does not establish physical persistence. GPU synchronization is not
added to timings; CPU transfer calls can themselves wait for GPU work.

After the production process has exited, run these host-only diagnostics with
the existing conda Python (h5py/numpy/torch; no simulator imports or installation):

```bash
PYTHONDONTWRITEBYTECODE=1 /home/tangyuan/miniconda3/envs/autodata/bin/python \
  workspace-overlays/openarm-production/test_export_timing.py

# Whole saved episode, upstream stack/write methods; scratch file is removed.
PYTHONDONTWRITEBYTECODE=1 /home/tangyuan/miniconda3/envs/autodata/bin/python \
  workspace-overlays/openarm-production/replay_export.py \
  AutoData/datasets/openarm_left_num_envs_8.hdf5 \
  --report workspace-overlays/openarm-production/runtime/export-replay-demo0.json

# Same real RGB frame subset and chunk shape, gzip-2 / none / LZF, rotated order.
PYTHONDONTWRITEBYTECODE=1 /home/tangyuan/miniconda3/envs/autodata/bin/python \
  workspace-overlays/openarm-production/benchmark_export.py \
  AutoData/datasets/openarm_left_num_envs_8.hdf5 --frames 32 --repeats 3 \
  --report workspace-overlays/openarm-production/runtime/export-compression-demo0.json
```

Use a fresh report name on subsequent runs. Diagnostics refuse unfinished run
manifests and retain normal HDF5 locking. Source datasets are opened read-only;
scratch outputs use the source filesystem and are deleted. The replay requires
memory for original CPU frames plus stacked data; do not run beside production
without budgeting this memory. It compares exported values blockwise.

Offline replay measures a saved CPU trajectory, not live GPU transfer, scene
metadata or concurrent simulation costs. Compression comparisons write different
byte counts, so their difference is not an exact isolated gzip time. Both tools
measure post-close `fsync` separately; this is diagnostic and is not added to the
production exporter. Small replay results must not be extrapolated as full-run
speedups or disk capacity benchmarks.

## Compatibility fixes tested in the local runtime

- Restore the original AutoData environment and planner registrations from `reference/`.
- Parse explicit cube attachment and the failure budget from the original YAML.
- Load the OpenArm URDF from the package and select the correct active arm.
- Preserve the passive arm's lock map when cuRobo changes the gripper state.
- Respect the TCP contact-offset direction, gripper-closing direction and warmup setting.
- Reorder interleaved simulator joints before cuRobo forward kinematics.
- Honor translation scale 0.02, rotation scale 0.10 and normalized action limit 0.2.
- Enable gradients only inside the planning call while simulation uses inference mode.
- Check completion even when planning fails before enqueuing an action.
- Optionally hold the final waypoint before checking/exporting the episode.
- Check the completion report in a parent process, since Isaac Sim shutdown can mask
  Python exceptions with an exit code of zero.

`prepare.py` generates the patched planner/adapter copies from the actual checkout
with exact source-anchor guards. `compat.py` loads them after Isaac Sim starts.
No dependency installations, conda modifications or upstream edits are performed.
An early test before the action-scaling/kinematics fixes completed with 0/1 success;
its evidence is retained in `runtime/original-gradfix*` and `generation-gradfix.log`.
An intermediate run was interrupted after discovering the scaling error.

## Rebuild on another machine

Place this overlay in the same repository-relative directory and run:

```bash
python workspace-overlays/openarm-production/prepare.py /path/to/openarm_pick_place_arena_20261013_120511.zip
```

The destination must not exist. `--destination` can build into a fresh directory for
inspection. Preparation verifies all 181 manifest entries against their SHA256
hashes before copying selected files. `runtime/` is ignored by Git; it includes the
prepared assets, source HDF5 copy and test outputs and must be copied separately for
an identical reproduction. Do not overwrite it while a process is using it.

Host-only checks (PyYAML required, no simulation imports):

```bash
PYTHONDONTWRITEBYTECODE=1 /home/tangyuan/miniconda3/envs/autodata/bin/python workspace-overlays/openarm-production/check_static.py
bash -n workspace-overlays/openarm-production/run-local.sh
```

A separate real right-arm environment/reset/three-step and action-scaling probe is
available through `bash workspace-overlays/openarm-production/run-local.sh --check-runtime`.
Its result is saved in `runtime-check-result.json`; it is not a data-generation test.
