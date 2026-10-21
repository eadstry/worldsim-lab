# OpenArm task completion and joint target error

This workspace overlay evaluates complete cube pick-and-place attempts in the frozen scene used by the 2026-10-20 generation run. It does not edit production configuration, upstream checkouts, training datasets or sealed reports.

## Acceptance protocol

The robot tracks the recorded TCP pose path with a shared feedback controller. Reference progress pauses outside a 15 mm / 0.18 rad tracking gate. Each attempted task starts from one of the four recorded initial states. A speed intervention changes reference progress, not the controller rate. This differs intentionally from the earlier fixed joint-target replay: it measures the response of a task-executing control stack.

Success requires all of the following in order:

- The cube was lifted at least 30 mm above its restored initial center height.
- The release phase and open command were reached, and both fingers actually exceed 0.3 rad.
- The original full-footprint placement condition holds: cube inside scanned pad, bottom height within 8 mm, linear speed at most 0.03 m/s and angular speed at most 0.5 rad/s.
- These placement conditions remain true for 0.5 simulated seconds.

Every attempt, including timeout and fall, is saved. Each condition uses the same four initial states and three repeats (12 paired attempts). A baseline-only pilot establishes whether the shared policy is operational before the comparison matrix is frozen. Pilot initialization errors and controller-development runs are reported separately from the final experiment.

## Conditions

The main comparison retains baseline, stiffness ×0.5 / ×2, damping ×0.5 / ×2, gravity feedforward, reference speed ×0.5 / ×2, and cube friction ×0.5 / ×2. All retain the cube and task. The earlier no-cube ablation, actuator-limit relaxations and control-frequency ablation become diagnostic background, not task-performance comparisons.

Physics comparisons use baseline drive parameters at 60, 120, 240 and 480 Hz, always 30 Hz control. Separate baseline cases change position iterations 16→32, velocity iterations 4→8, or external-forces-every-iteration false→true. Each changes one field. Effective parameters and source hashes are saved per run. GPU initialization and runtime property verification must pass before a case is interpreted.

## Metrics and interpretation

Main action/state arrays contain absolute joint radians in the same joint order, not end-effector deltas. Arm metrics exclude the two fingers. `request_pre` compares the newly computed absolute request with the position before the control step; `request_post` uses the resulting position. Physics-substep metrics separately compare request/applied and applied/state at synchronized times.

Report success numerator/denominator first, then all-attempt MAE and p95, successful-attempt MAE, elapsed simulated time and per-phase coverage/error. Missing phases remain missing. Aggregate per attempt, not by pooling frames from tasks of different duration. Never rank a failed low-motion episode as a superior controller because it has small MAE. Use paired initial-state comparisons; repeats assess reproducibility and are not independent randomized robot populations. Results apply to this frozen scene, source pose routes and feedback controller.

## Invocation

Submit `bash workspace-overlays/openarm-task-error/run.sh ...` through the shared host queue. Required arguments: `--source` (historical HDF5), `--runtime` (frozen package and compat.py), `--autodata-root` (dependency imports), `--output` (new directory). No upstream entrypoint is executed or modified. Use the already configured host interpreter; do not install simulation dependencies.

The wrapper requires an experiment completion receipt because simulator shutdown can return success after an initialization exception. `error.txt`, absent receipts and non-finite arrays invalidate the run. `--max-frames` is for explicit short diagnostics, not a task-performance result.

Host checks: `python -m unittest discover -s workspace-overlays/openarm-task-error -p 'test_*.py'` in the configured NumPy environment. GPU outputs stay under `runs/` and are never staged.

## Independent placement audit

The original acceptance counts remain the primary protocol. Some timeout attempts show a stationary cube pose with substantial raw PhysX velocity readback; these are criterion disagreements until the geometric and angular conditions are inspected. `diagnostic.py` instruments the unchanged runner in memory with read-only cube orientation, angular velocity, geometry-only placement and a final ten-second physics-step buffer. It saves both base and expanded code hashes. `audit_acceptance.py` reconstructs the original counts, then reports a separate pose-difference stability criterion with the same geometry, lift, release, speed thresholds and hold time. `audit_physics_steps.py` inspects only timeout windows: early-completed environments continue simulating, so their final batch buffers are outside their task windows.

The 192-attempt primary matrix is accompanied by 12 baseline attempts matching the four-environment physics-comparison layout and 84 acceptance audits (80 matching the full forty-environment layout, plus four at 240 Hz). These sets remain separate. Physics comparisons additionally report the same matched attempts accepted at every frequency, alongside all attempts; this exposes duration/acceptance selection effects. Host tests cover independent acceptance guards and quaternion sign equivalence. Original success terminates recording, so an unconfirmed independent hold at that cutoff is reported as censored. High frequency pose jitter can be missed at 30 Hz; final physics-step buffers expose that case. Neither simulator-returned velocities nor pose differences silently replace the primary criterion. Twenty preliminary simulation attempts completed with arrays but lacked integration receipts because simulator shutdown skipped a caller finally block; their queue failures and development data remain separate. The corrected diagnostic writes its integration receipt immediately after output creation.
