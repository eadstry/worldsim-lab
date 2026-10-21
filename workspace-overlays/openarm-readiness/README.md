# OpenArm readiness and isolated export regression

This task executes prerequisites for the registered **24-environment** OpenArm
capability experiments. An eight-environment regression is a diagnostic of export
closure, not a substitute qualification or a reduction of formal parallelism.

`audit.py` reads an existing HDF5 without modifying it, scans every RGB frame with
bounded working buffers, separates initial warmup from persistent near-black
frames, separates historical telemetry by run ID, and invokes the existing
24-environment resource admission probe. Image intensity rules flag suspected
blackout; they do not establish semantic visibility, calibration or training
usefulness. Input size/mtime are checked for concurrent modification. It does not
run simulation, training, delete data, or install dependencies.

`regression.py` claims a brand-new directory using exclusive `mkdir`, verifies a
source manifest, and uses frozen copies of the existing fixed-attempt launcher,
resource guards and terminal predicate. It runs exactly eight attempts in eight
environments, seed 606, auto export, three 640×480 RGB streams, 60 final-hold
steps, original control rate and gzip2. Failed attempts are retained and there
are no automatic retries. The inherited producer guard stops on RSS >44 GiB,
effective available RAM <8 GiB, disk reserve <70 GiB, or 2400-second batch timeout.
Independent readback checks every recorded dataset, per-array hashes, camera
structure, success counts and the unchanged recorded-terminal predicate. It is
not independent physics replay or a camera-usability check. Validation aligns
reads to HDF5's time chunks where a 96 MiB block limit permits.

## Run

Use the already configured AutoData Python, not a newly installed environment.
All full scans and simulations must use the same host-local task queue. Do not
change queued/running scripts, runtime copies, task descriptor or manifests.
Snapshot and output paths below are explicit placeholders; no resume is allowed.

```bash
python -B -m unittest discover -s workspace-overlays/openarm-readiness -v
python audit.py --source /existing/source.hdf5 \
  --export-directory /existing/failed-batch \
  --preflight /frozen/preflight.py --protocol /frozen/protocol.json \
  --output /new/audit-directory
python regression.py --snapshots /frozen/snapshots \
  --source-manifest /frozen/manifest.json \
  --autodata-root /configured/AutoData --output /new/regression-directory
```

The snapshot directory needs `export-source-snapshot/` (production Python files
and prepared `runtime/`), `capacity-snapshot/` (`run.py`, `produce.py`, `launch.py`),
`gate-snapshot/` (`terminal_gate.py`, `bench32.py`) and `regression-task.yaml`.
Record SHA256 for snapshot files and the read-only upstream Python dependencies
in the source manifest; do not include credentials, environment snapshots or
unrelated data. Prepared runtime assets and source HDF5 remain machine-local,
not Git payloads. This run's concrete provenance is saved with the local results.

Host tests cover initial black frames vs persistent blackout, malformed streams,
separation of interleaved run IDs, exclusive output ownership, dependency changes,
failed-route retention, exact chunked hashes and rejection of bad terminal labels
or nonfinite data. Existing export-pool spawn regression tests are also run on a
frozen source snapshot. No upstream checkout, environment or published output
is modified.
