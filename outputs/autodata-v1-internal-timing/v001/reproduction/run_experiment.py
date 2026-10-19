# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Prepare immutable v1 launcher copies, then run sync and auto sequentially."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False))
    temporary.replace(path)


def prepare(directory, trials, num_envs):
    suite = Path(__file__).resolve().parent
    root = suite.parents[1]
    frozen = root / "AutoData/datasets/efficiency_20261014_201834/v1/launchers/v1"
    original_manifest = json.loads((frozen.parents[1] / "preparation.json").read_text())
    directory.mkdir(parents=True, exist_ok=False)
    launcher = directory / "launchers/v1"
    launcher.mkdir(parents=True)
    hashes = {}
    for source in sorted(frozen.iterdir()):
        if source.is_file() and source.suffix in (".py", ".sh"):
            expected = original_manifest["source_sha256"].get(f"launchers/v1/{source.name}")
            assert expected is not None or source.suffix == ".sh", f"Unrecorded Python source: {source}"
            expected = expected or sha(source)
            assert sha(source) == expected, f"Frozen v1 source changed: {source}"
            shutil.copy2(source, launcher / source.name)
            hashes[source.name] = expected
    runtime = (frozen / "runtime").resolve(strict=True)
    (launcher / "runtime").symlink_to(runtime, target_is_directory=True)
    generate = launcher / "generate.py"
    source = generate.read_text()
    anchor = "    return source\n"
    assert source.count(anchor) == 1
    generate.write_text(source.replace(anchor,
        "    from internal_timing import instrument_source\n    return instrument_source(source)\n", 1))
    shutil.copy2(suite / "internal_timing.py", launcher / "internal_timing.py")
    task = runtime / "openarm_autodata/tasks/pick_place/autodata_configs/tasks/openarm_bimanual_left_pick_place.yaml"
    shutil.copy2(task, directory / "task.yaml")
    input_file = runtime / "inputs/openarm_left_fixture_clearance_source.hdf5"
    assert input_file.is_file()
    runtime_sources = {str(p.relative_to(runtime)): sha(p) for p in sorted(runtime.rglob("*"))
                       if p.is_file() and p.suffix in (".py", ".yaml", ".json", ".urdf")
                       and "__pycache__" not in p.parts}
    plan = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
            "state": "prepared", "root": str(root), "launcher": str(launcher),
            "python": "/home/tangyuan/miniconda3/envs/autodata/bin/python",
            "source_input": str(input_file), "source_sha256": sha(input_file),
            "task_sha256": sha(task), "seed": 101, "num_envs": num_envs, "target_successes": trials,
            "final_hold_steps": 60, "queue_memory_gib": 16,
            "variants": [{"name": "before_sync", "workers": "0"},
                         {"name": "after_auto", "workers": "auto"}],
            "frozen_launcher_sha256": hashes,
            "instrumented_launcher_sha256": {p.name: sha(p) for p in sorted(launcher.glob("*.py"))},
            "runtime_root": str(runtime), "runtime_source_sha256": runtime_sources,
            "upstream_head": subprocess.check_output(["git", "-C", str(root / "AutoData"), "rev-parse", "HEAD"], text=True).strip(),
            "measurement": "exclusive host main-thread wall/CPU; no CUDA fences; all variants use identical hooks",
            "limitations": ["One pair at one fixed seed, not a statistical population estimate",
                            "Host API time is not isolated GPU kernel time",
                            "Execute windows overlap across concurrent environments"]}
    save(directory / "experiment.json", plan)
    for variant in plan["variants"]:
        (directory / variant["name"]).mkdir()
    return plan


def run(directory, plan):
    assert plan["state"] == "prepared", "Use a fresh prepared directory; started runs are never overwritten"
    root, launcher = Path(plan["root"]), Path(plan["launcher"])
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,uuid,utilization.gpu,memory.used,memory.total",
                          "--format=csv,noheader"], capture_output=True, text=True)
    assert gpu.returncode == 0, "GPU unavailable; run on the configured GPU host outside the sandbox"
    plan["gpu_preflight"] = gpu.stdout.strip()
    minimum_disk_gib = plan["target_successes"] * 1.5 + 1
    assert shutil.disk_usage(directory).free > minimum_disk_gib * 1024**3, f"Need at least {minimum_disk_gib} GiB free for the paired RGB runs"
    plan["state"] = "running"
    save(directory / "experiment.json", plan)
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    for variant in plan["variants"]:
        output = directory / variant["name"] / "episodes.hdf5"
        command = ["bash", str(launcher / "run-local.sh"), "--autodata-root", str(root / "AutoData"),
                   "--arm", "left", "--final-hold-steps", "60", "--input_file", plan["source_input"],
                   "--output_file", str(output), "--task_descriptor", str(directory / "task.yaml"),
                   "--num_envs", str(plan["num_envs"]), "--generation_num_trials", str(plan["target_successes"]),
                   "--export-workers", variant["workers"], "--export-queue-memory-gib", "16",
                   "--export-timeout-seconds", "600", "--log-interval", "10"]
        variant.update(command=command, state="running", started_at=datetime.now(timezone.utc).isoformat())
        save(directory / "experiment.json", plan)
        print(f"Starting {variant['name']}; output={output}", flush=True)
        started = time.monotonic()
        with output.with_suffix(".launcher.log").open("x") as log:
            result = subprocess.run(command, cwd=root, env=environment, stdout=log, stderr=subprocess.STDOUT)
        variant.update(returncode=result.returncode, launcher_wall_seconds=time.monotonic() - started,
                       ended_at=datetime.now(timezone.utc).isoformat(),
                       state="generated" if result.returncode == 0 else "failed")
        save(directory / "experiment.json", plan)
        if result.returncode:
            plan["state"] = "failed"
            save(directory / "experiment.json", plan)
            raise RuntimeError(f"{variant['name']} failed; see {output.with_suffix('.console.log')}")
        validators = {
            "physical": [plan["python"], str(launcher / "validate_output.py"), str(output)],
            "schema": [plan["python"], str(root / "AutoData/scripts/validate_dataset.py"), str(output)],
        }
        for name, check in validators.items():
            with output.with_suffix(f".{name}.log").open("x") as log:
                validated = subprocess.run(check, cwd=root, env=environment, stdout=log, stderr=subprocess.STDOUT)
            variant[f"{name}_validation_returncode"] = validated.returncode
        variant["state"] = "complete"
        save(directory / "experiment.json", plan)
        print(f"Completed {variant['name']} in {variant['launcher_wall_seconds']:.1f}s", flush=True)
    plan["state"] = "complete"
    save(directory / "experiment.json", plan)
    subprocess.run([plan["python"], str(Path(__file__).with_name("verify_pair.py")), str(directory)], check=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name("analyze.py")), str(directory)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--trials", type=int, default=16)
    parser.add_argument("--num-envs", type=int, default=8)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--run-prepared", action="store_true")
    args = parser.parse_args()
    assert args.num_envs > 0 and args.trials >= 2 * args.num_envs, "At least two environment waves are needed to expose export stalls"
    directory = args.directory.resolve()
    plan = json.loads((directory / "experiment.json").read_text()) if args.run_prepared else prepare(directory, args.trials, args.num_envs)
    if not args.prepare_only:
        run(directory, plan)
    print(directory, flush=True)


if __name__ == "__main__":
    main()
