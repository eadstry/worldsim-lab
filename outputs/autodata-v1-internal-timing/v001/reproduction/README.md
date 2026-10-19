# v1 internal timing comparison

This opt-in experiment uses the frozen v1 launchers from the 2026-10-14 efficiency
run. The treatment is `--export-workers auto`; the control is synchronous export
(`0`). The treatment includes the frozen asynchronous path's existing recorder
ownership and shared-memory packing changes. It is not a cuRobo v1/v2 comparison.

Preparation verifies the archived Python files against their recorded hashes,
copies the launcher into a new run directory, and adds a source-transformation
hook only to that copy. Both variants reference the same existing v1 runtime and
input. Upstream files, existing launchers and conda dependencies are not edited.

Run on the configured GPU host (the desktop sandbox has no NVIDIA device nodes):

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  workspace-overlays/openarm-v1-timing/run_experiment.py \
  --directory runs/v1-internal-timing-NEW --prepare-only

PYTHONDONTWRITEBYTECODE=1 python3 \
  workspace-overlays/openarm-v1-timing/run_experiment.py \
  --directory runs/v1-internal-timing-NEW --run-prepared
```

Each variant targets 16 successes across eight environments with seed 101 and
60 final hold steps. The runs execute sequentially to avoid GPU contention. A
minimum of 25 GiB free disk space is checked before the default pair. Use
`--num-envs 4 --trials 8` during preparation for the smaller paired workload.
The 2026-10-15 initial 8-env pilot was SIGKILLed before its first completed
episode and had an OOM-kill counter increase; the formal pair uses four envs.
Raw RGB datasets
and journals stay under ignored `runs/`; reports can be copied to a new sealed
`outputs/` version after completion. Existing run directories are never reused
by preparation. Resume is only for a prepared directory with no started runs.

## Measurement

`internal_timing.py` partitions the main thread's wall and thread CPU time into
exclusive synchronous scopes. Child time is excluded from parent categories,
including at snapshots taken while a parent scope is still open. The primary
global window starts immediately before the environment loop and ends when it
returns. A separate window extends through final output readiness and shutdown.

The hooks cover action preparation/processing/application, scene writes and
updates, physics API calls, rendering, camera pose updates, RGB readback/copy,
observation computation, recorder buffers, planning, resets, producer export,
shared-memory packing, export polling/backpressure, drain and merge. Remaining
time stays explicitly in scheduler or unattributed categories.

Each completed `MultiWaypoint.execute` snapshots this same timeline at entry and
return. It therefore records what the main thread was doing while that action
was pending, including work for other environments. These eight concurrent
windows overlap and must not be added to obtain whole-run time. Queue `join()`
is also measured as an inclusive logical wait, not as idle CPU or a separate
additive category. Cancelled execute calls are counted but excluded from the
completed-call decomposition.

No extra CUDA synchronization is introduced. These are host API latency shares,
not isolated GPU kernel occupancy. A later RGB copy may absorb deferred GPU
work. Async worker writing overlaps the producer; its durations remain in the
existing export journals and are not added to the producer wall-time partition.
Both variants use identical hooks; instrumentation perturbation is not assumed
to be zero. One fixed-order pair cannot establish broad speedup significance.

## Validation

Host-only accounting and queue semantics checks:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  workspace-overlays/openarm-v1-timing/test_internal_timing.py
```

These do not validate simulation. The experiment runner performs real GPU
generation and invokes both the existing physical terminal-state validator and
the upstream dataset schema validator after each run. `analyze.py` additionally
checks that every completed execute and both global windows sum to their
recorded wall durations. Physical/schema failures are preserved in the report.

The frozen runtime is machine-local and is not bundled with this directory.
`experiment.json` records input, launcher and runtime-source hashes for audit;
that record does not make missing assets portable or prove annotations correct.
