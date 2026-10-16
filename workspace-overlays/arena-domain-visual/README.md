# Arena domain-randomization visual checks

Run Arena's nine concrete Variation classes, plus PoseRange, through the actual
ArenaEnvBuilder on a minimal cube/two-sphere scene. This is local no-policy
inspection, not an Experiment Runner evaluation or a robot planning benchmark.
The ready native Arena `.venv` is reused without dependency installation or
upstream edits. The original prepared Arena workspace is passed explicitly;
this task worktree deliberately leaves its own submodules uninitialized.

```bash
python3 scripts/task-queue.py submit --name arena-domain-visual --timeout 900 -- \
  env OMNI_KIT_ACCEPT_EULA=YES ACCEPT_EULA=Y PYTHONDONTWRITEBYTECODE=1 \
  /home/tangyuan/WorldSimReady-Home/IsaacLab-Arena/.venv/bin/python \
  workspace-overlays/arena-domain-visual/run.py \
  --arena-root /home/tangyuan/WorldSimReady-Home/IsaacLab-Arena \
  --output runs/arena-domain-visual-NEW
```

The output must not exist. Optional `--only extrinsics,mass` selects independent
cases. Do not edit a queued or running launcher. The five build-time lighting/HDR
variations rebuild the environment for each value. Camera, mass and disappearance
variations reset the environment and replace the sampler passed to their native
event. Degenerate Uniform ranges and Bernoulli probability endpoints isolate A/B
effects; only PoseRange uses genuine interval samples at two seeds. This does not
test the statistical distribution or estimate policy success rates.

Camera initial poses are composed into CameraCfg before building, keeping USD and
physics views consistent. The extrinsics comparison uses optical X ±30 mm for
visibility, beyond the class's default ±5 mm. Intrinsics use the default ±10%
fractional fx/fy range endpoints. Camera pose and aperture changes are read back.

The mass comparison uses global zero gravity and the same 0.05 N world-X force
for 48 physics steps (0.4 s). It checks applied masses and the ratio of observed
displacements. Direct permanent-wrench composition preserves the public current
Isaac Lab API; no deprecated force setter or compensating physics edits are used.
This controlled free-body test is not a contact-rich manipulation experiment.

HDRImageVariation selects two genuine HDR files already bundled with the local
Isaac Sim installation, registered under task-local names. HDR files are read locally rather than downloaded. File paths are machine-local
and must exist in the chosen runtime. The GroundPlane retains Arena's existing
asset configuration, which resolves through the runtime's URL/cache mechanism.

For the 2026-10-16 check, the first run passed eight cases. Extrinsics exposed a
test-camera initialization mismatch; the first mass test contacted the ground
and failed the inverse-mass check. Both failures and their original source hashes
are preserved. After correcting the test setup, the two cases passed. The gallery
uses the first eight successful cases and the two successful rechecks, with explicit
per-case run provenance. No first-run failure is reclassified or erased.

After those runs complete, build the local artifact and inline gallery using a
ready Python with Pillow (the existing Arena Python suffices):

```bash
python workspace-overlays/arena-domain-visual/package.py \
  --first runs/arena-domain-visual-r01 --recheck runs/arena-domain-visual-r02 \
  --arena-root /home/tangyuan/WorldSimReady-Home/IsaacLab-Arena \
  --output outputs/arena-domain-visual/vNEW \
  --widget /absolute/writable/path/arena-domain-visual.html
```

Packaging asserts complete coverage of all concrete Variation subclasses and
passing outcomes. PNG pairs, raw failure/recheck results and source hashes are
sealed with a manifest. The inline view embeds compressed versions of those real
frames. Source root HEAD and local-change presence are recorded; this checks the
current local Arena tree, not a pristine upstream commit or AutoData's embedded
Arena. PhysX was checked; Newton, trained policies and motion planning were not.
