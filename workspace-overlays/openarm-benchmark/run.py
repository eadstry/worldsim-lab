#!/usr/bin/env python3
"""Plan or execute the OpenArm benchmark without installing runtime dependencies."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXTERNAL_ENVIRONMENT = "openarm_benchmark.environment:OpenArmBenchmarkEnvironment"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def bundle_path(bundle, relative):
    path = (bundle / relative).resolve()
    if not path.is_relative_to(bundle.resolve()) or not path.is_file():
        raise ValueError(f"Missing or external bundle file: {relative}")
    return path


def verify_bundle(bundle, lock):
    manifest_path = bundle_path(bundle, "MANIFEST.json")
    if sha256(manifest_path) != lock["bundle_manifest_sha256"]:
        raise ValueError("OpenArm delivery manifest differs from the recorded input")
    entries = read_json(manifest_path)["files"]
    for entry in entries:
        path = bundle_path(bundle, entry["path"])
        if path.stat().st_size != entry["bytes"] or sha256(path) != entry["sha256"]:
            raise ValueError(f"Bundle content changed: {entry['path']}")
    return {"status": "verified", "files_checked": len(entries), "manifest_sha256": sha256(manifest_path)}


def inspect_arena(arena_root, lock):
    if not (arena_root / "isaaclab_arena/evaluation/policy_runner.py").is_file():
        raise ValueError("--arena-root must contain isaaclab_arena/evaluation/policy_runner.py")
    # An exported source tree can have no .git, but its critical API files must match.
    matched = []
    for version in lock["arena_versions"]:
        if all(
            (arena_root / relative).is_file() and sha256(arena_root / relative) == digest
            for relative, digest in version["api_files"].items()
        ):
            matched.append(version)
    if len(matched) != 1:
        raise ValueError("Arena API files differ from both recorded revisions; review compatibility first")
    version = matched[0]
    return {"revision": version["revision"], "task_api": version["task_api"], "check": "critical_source_hashes"}


def validate_protocol(protocol):
    if protocol.get("schema_version") != 1 or protocol.get("environment") != "openarm_left_pick_place_benchmark":
        raise ValueError("Unsupported benchmark schema or environment")
    cases = protocol.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("The benchmark needs at least one case")
    names = set()
    for case in cases:
        name = case["name"]
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name) or name in names:
            raise ValueError("Case names must be unique portable identifiers")
        names.add(name)
        if case["group"] not in {"smoke", "regression", "baseline"}:
            raise ValueError("Unknown case group")
        for field in ("num_envs", "num_episodes"):
            if type(case[field]) is not int or case[field] <= 0:
                raise ValueError(f"{field} must be a positive integer")
        horizon = case["episode_length_s"]
        if type(horizon) not in (int, float) or not math.isfinite(horizon) or horizon <= 0:
            raise ValueError("Episode horizon must be finite and positive")
        seeds = case["seeds"]
        if not seeds or any(type(seed) is not int or seed < 0 for seed in seeds) or len(set(seeds)) != len(seeds):
            raise ValueError("Seeds must be distinct nonnegative integers")
        if case["expected"] not in {"all_failed", "all_succeeded"}:
            raise ValueError("Unknown demonstration expectation")
        fixture = case.get("fixture")
        if fixture is not None and case["group"] != "regression":
            raise ValueError("Fixed initial states are allowed only for regression")
        if case["policy_type"] == "zero_action":
            if fixture is not None or case["expected"] != "all_failed":
                raise ValueError("Zero-action checks require randomized resets and expected failures")
        elif case["policy_type"] == "openarm_arena.policy.OpenArmFixtureReplayPolicy":
            if case["group"] != "regression" or not fixture or case["expected"] != "all_succeeded":
                raise ValueError("Replay must use a fixed regression state and expect success")
        else:
            raise ValueError("This no-model example supports zero action and fixture replay only")


def make_plan(protocol, group, bundle, arena_root, runtime_python, output_dir):
    runs = []
    for case in protocol["cases"]:
        if not (case["group"] in {"smoke", "regression"} if group == "all" else case["group"] == group):
            continue
        for seed in case["seeds"]:
            run_name = f"{case['name']}_seed{seed}"
            command = [
                str(runtime_python), str(ROOT / "runtime.py"),
                "--bundle", str(bundle), "--arena-root", str(arena_root), "--",
                "--viz", "none", "--enable_cameras",
                "--kit_args", "--enable omni.usd.schema.omni_lens_distortion",
                "--external_environment_class_path", EXTERNAL_ENVIRONMENT,
                "--policy_type", case["policy_type"],
                "--num_envs", str(case["num_envs"]), "--env_spacing", "2",
                "--seed", str(seed), "--num_episodes", str(case["num_episodes"]),
                "--output_base_dir", str(output_dir / run_name),
            ]
            if case["fixture"]:
                command += ["--fixture_path", str(bundle_path(bundle, case["fixture"]))]
            command += [protocol["environment"], "--openarm_episode_length_s", str(case["episode_length_s"])]
            if case["fixture"]:
                command += ["--openarm_replay_fixture", str(bundle_path(bundle, case["fixture"]))]
            runs.append({"name": run_name, "case": case, "seed": seed, "command": command})
    if not runs:
        raise ValueError("No cases selected")
    return runs


def collect_result(run_dir, case, seed):
    paths = sorted(run_dir.rglob("episode_results_rank*.jsonl"))
    if not paths:
        raise ValueError("No completed episode records")
    if len({path.parent for path in paths}) != 1:
        raise ValueError("Expected exactly one Arena run directory")
    rows = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    if len(rows) < case["num_episodes"]:
        raise ValueError(f"Incomplete rollout: {len(rows)} / {case['num_episodes']} episodes")
    identities = set()
    for row in rows:
        if type(row.get("success")) is not bool:
            raise ValueError("Episode success must be a boolean")
        if row.get("seed") != seed:
            raise ValueError("Recorded seed differs from the requested seed")
        if type(row.get("episode_length")) is not int or row["episode_length"] <= 0:
            raise ValueError("Invalid episode length")
        identity = (row["env_id"], row["episode_in_env"])
        if identity in identities:
            raise ValueError("Duplicate completed episode")
        identities.add(identity)
    report = paths[0].parent / "index.html"
    if not report.is_file() or report.stat().st_size == 0:
        raise ValueError("Arena HTML report is missing or empty")
    successes = sum(row["success"] for row in rows)
    expected_met = successes == (len(rows) if case["expected"] == "all_succeeded" else 0)
    return {
        "completed_episodes": len(rows), "successes": successes,
        "failures": len(rows) - successes, "success_rate": successes / len(rows),
        "mean_episode_steps": sum(row["episode_length"] for row in rows) / len(rows),
        "expected": case["expected"], "expectation_met": expected_met,
        "arena_report": report.relative_to(run_dir.parent).as_posix(),
        "episode_files": [path.relative_to(run_dir.parent).as_posix() for path in paths],
    }


def write_report(output_dir, results):
    table_rows = []
    for result in results:
        metrics = result.get("metrics", {})
        table_rows.append("<tr>" + "".join(
            "<td>" + html.escape(str(value)) + "</td>" for value in (
                result["name"], result["status"], metrics.get("completed_episodes", "—"),
                metrics.get("successes", "—"), metrics.get("success_rate", "—"), result.get("error", ""),
            )
        ) + "<td>" + (
            '<a href="' + html.escape(metrics["arena_report"], quote=True) + '">Arena 报告</a>'
            if "arena_report" in metrics else "—"
        ) + "</td></tr>")
    content = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>OpenArm benchmark 示例结果</title><style>body{font:16px system-ui;margin:40px;max-width:1100px}
table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:10px;text-align:left}</style>
<h1>OpenArm benchmark 示例结果</h1><p>检查通过表示预期链路行为成立。零动作失败和固定轨迹成功均不是学习策略的泛化成绩。</p>
<table><tr><th>检查</th><th>执行状态</th><th>完成回合</th><th>成功回合</th><th>任务成功率</th><th>错误</th><th>详情</th></tr>
""" + "".join(table_rows) + "</table></html>"
    (output_dir / "index.html").write_text(content, encoding="utf-8")


def execute_plan(runs, output_dir, metadata):
    # A new directory prevents stale episode rows from appearing to satisfy this run.
    output_dir.mkdir(parents=True, exist_ok=False)
    manifest = {**metadata, "status": "running", "runs": []}
    write_json(output_dir / "benchmark_result.json", manifest)
    try:
        for run in runs:
            result = {"name": run["name"], "status": "running", "command": run["command"]}
            manifest["runs"].append(result)
            write_json(output_dir / "benchmark_result.json", manifest)
            print(f"Running {run['name']}", flush=True)
            try:
                with (output_dir / (run["name"] + ".log")).open("w", encoding="utf-8") as log:
                    completed = subprocess.run(run["command"], stdout=log, stderr=subprocess.STDOUT, check=False)
                result["returncode"] = completed.returncode
                if completed.returncode != 0:
                    raise ValueError(f"Arena exited with code {completed.returncode}; see the preserved log")
                result["metrics"] = collect_result(output_dir / run["name"], run["case"], run["seed"])
                if not result["metrics"]["expectation_met"]:
                    raise ValueError("Observed task outcome differs from the demonstration expectation")
                result["status"] = "passed"
            except (OSError, ValueError, KeyError) as error:
                result.update(status="failed", error=str(error))
                break
        manifest["status"] = "passed" if (
            len(manifest["runs"]) == len(runs) and all(run["status"] == "passed" for run in manifest["runs"])
        ) else "failed"
    except BaseException:
        manifest["status"] = "interrupted"
        raise
    finally:
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(output_dir / "benchmark_result.json", manifest)
        write_report(output_dir, manifest["runs"])
    return manifest["status"] == "passed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True, help="Unmodified OpenArm delivery directory")
    parser.add_argument("--arena-root", type=Path, required=True)
    parser.add_argument("--runtime-python", type=Path, required=True, help="Already configured Isaac Sim Python")
    parser.add_argument("--protocol", type=Path, default=ROOT / "benchmark.json")
    parser.add_argument("--case", choices=("all", "smoke", "regression", "baseline"), default="all")
    parser.add_argument("--output-dir", type=Path, required=True, help="New output directory; never reused")
    parser.add_argument("--dry-run", action="store_true", help="Verify inputs and print commands; no simulator or output writes")
    args = parser.parse_args()
    try:
        bundle, arena_root, runtime_python, output_dir = (
            path.expanduser().absolute() for path in (args.bundle, args.arena_root, args.runtime_python, args.output_dir)
        )
        if output_dir.exists():
            raise ValueError("--output-dir must not exist; choose a new directory")
        if not runtime_python.is_file() or not os.access(runtime_python, os.X_OK):
            raise ValueError("--runtime-python must be an executable from a configured simulation environment")
        lock = read_json(ROOT / "input-lock.json")
        bundle_check = verify_bundle(bundle, lock)
        arena_check = inspect_arena(arena_root, lock)
        protocol = read_json(args.protocol)
        validate_protocol(protocol)
        runs = make_plan(protocol, args.case, bundle, arena_root, runtime_python, output_dir)
        metadata = {
            "schema_version": 1, "benchmark_id": protocol["benchmark_id"], "scope": protocol["scope"],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "protocol_sha256": sha256(args.protocol), "input_lock_sha256": sha256(ROOT / "input-lock.json"),
            "bundle_check": bundle_check, "arena_check": arena_check,
            "selected_case": args.case, "planned_runs": len(runs),
            "runtime_validation": "not_performed" if args.dry_run else "see_run_results",
        }
        if args.dry_run:
            print(json.dumps({**metadata, "status": "planned", "runs": runs}, ensure_ascii=False, indent=2))
            return 0
        return 0 if execute_plan(runs, output_dir, metadata) else 1
    except (OSError, ValueError, KeyError) as error:
        print(f"OpenArm benchmark: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
