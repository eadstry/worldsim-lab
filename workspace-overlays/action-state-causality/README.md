# OpenArm action/state intervention experiment

This overlay tests causes of requested joint target versus measured joint angle differences. It does not tune a production controller or generate training demonstrations.

Run GPU commands through the host's shared `scripts/task-queue.py`. Use an existing Isaac environment; the overlay does not install simulation dependencies. `--runtime` points to a frozen copy of the prepared `openarm_autodata` package, and `--compat-root` contains the matching production `compat.py`. Preserve a hash manifest of that copy. `--autodata-root` supplies the existing upstream Python dependencies without modifying them.

```bash
python3 scripts/task-queue.py submit --name action-state-replay --timeout 1800 -- \
  bash workspace-overlays/action-state-causality/run.sh \
  --source /absolute/path/to/openarm-left.hdf5 \
  --runtime /absolute/path/to/frozen-runtime \
  --compat-root /absolute/path/to/frozen-runtime \
  --autodata-root /absolute/path/to/AutoData \
  --output /absolute/path/to/new-run --mode source
```

`source` mode restores one saved initial scene and replays the original seven-dimensional TCP/gripper actions through the original IK action terms. Compare its recorded requested targets and states against the historical episode before interpreting interventions. Cameras and unnecessary observations are disabled, and early-state agreement is checked from saved arrays. Full contact trajectories need not reproduce bit for bit.

`fixed` mode restores the same initial scene in independent environments and replays the saved absolute joint requests directly. It bypasses IK feedback so that a changed physical response cannot alter the requested path. The physical step remains 1/120 s. The baseline request is held for four physics substeps, with arm/finger target ramps of 2/1 rad/s. An independent baseline repeat estimates sensitivity to scene placement and solver variation.

Each named variant changes the indicated gain, time scale, target ramp, control period, cube presence, gravity feedforward, arm effort limits or arm physical velocity limits. Gain and physical limit changes apply only to the seven active arm joints. `rate_unbinding` changes only the arm target ramp; finger ramps remain at 1 rad/s. Slower/faster trajectories and the 15 Hz variant use explicit zero-order-hold sampling of the same recorded target sequence. These are interventions on command timing, not separately planned trajectories. The original production files are never edited.

`--no-collisions` disables the robot's collision shapes for an additional diagnostic batch. The spawn wrapper first removes USD geometry instancing in the ephemeral stage; it never writes asset files. The post-spawn audit counts enabled and disabled colliders and rejects an ineffective intervention. The generic collision configuration setter alone can skip instanceable geometry. This experiment cannot assess grasp success. Moving the cube away alone distinguishes cube interaction from the remaining scene contacts. Neither experiment by itself validates the geometry against a real gripper.

Each run saves runtime gains and metadata, control-step arrays, and (in fixed mode) all physics substeps. Control arrays pair requests with pre-step and post-step positions separately. The substep archive also contains states after a variant's own replay has ended while other variants finish; use each variant's control timestamps to select its valid replay interval. No measured solver drive-force claim is made: implicit PD torque estimates are not actual drive-force telemetry.

```bash
python workspace-overlays/action-state-causality/analyze.py \
  /absolute/path/to/run-root --output /absolute/path/to/new-analysis.json
```

The CPU analysis checks raw-array dimensions, finiteness and agreement with the saved summary, then reports differences relative to each batch's baseline. It excludes historical collision-disable attempts without an effective stage audit. At 15 Hz the pre-step and post-step statistics sample different phases of longer control intervals; compare the physics-substep residual before attributing a change to the physical controller. Intervention percentages are not additive components of the original error.

For the archived 2026-10-21 runs, the first `fixed-r01` implementation relaxed arm and finger ramps together in `rate_unbinding`; use the later arm-only `arm-limits-r02` condition for that comparison. Exact historical experiment sources and their matching hashes remain in the local run directory. The ineffective `no-collisions-r01` batch is excluded, and `no-collisions-r03` includes the effective stage audit. Gain, speed, gravity and cube interventions were repeated on a second saved episode. Raw traces and research results remain local rather than being included in the source synchronization.

Keep raw numeric outputs, assets and the Isaac environment outside Git. Conclusions from one scene and robot do not establish SO101 behavior or real-robot transfer performance.
