"""Host-only checks for provenance, scoring, failures, and task API conversion."""

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import types
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run as benchmark


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.protocol = benchmark.read_json(ROOT / "benchmark.json")
        self.case = self.protocol["cases"][0]

    def episodes(self, run_dir, successes=(False, False), seed=11):
        native_dir = run_dir / "native_timestamp"
        native_dir.mkdir(parents=True)
        rows = [dict(env_id=index, episode_in_env=0, seed=seed, success=success, episode_length=15)
                for index, success in enumerate(successes)]
        (native_dir / "episode_results_rank0.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows)
        )
        (native_dir / "index.html").write_text("<html>Native Arena report</html>")
        return native_dir

    def test_protocol_and_fixture_only_regression(self):
        benchmark.validate_protocol(self.protocol)
        self.protocol["cases"][0]["fixture"] = "fixtures/replay_left.npz"
        with self.assertRaisesRegex(ValueError, "only for regression"):
            benchmark.validate_protocol(self.protocol)

    def test_default_suite_keeps_full_budget_baseline_optional(self):
        (self.root / "fixtures").mkdir()
        (self.root / "fixtures/replay_left.npz").touch()
        plan = benchmark.make_plan(self.protocol, "all", self.root, self.root, Path(sys.executable), self.root)
        self.assertEqual([item["case"]["group"] for item in plan], ["smoke", "regression"])
        # The same fixture supplies both actions and reset state.
        plan = benchmark.make_plan(self.protocol, "regression", self.root, self.root, Path(sys.executable), self.root)
        command = plan[0]["command"]
        self.assertEqual(command[command.index("--fixture_path") + 1],
                         command[command.index("--openarm_replay_fixture") + 1])

    def test_bundle_integrity_and_external_file_rejection(self):
        payload = self.root / "asset.usd"
        payload.write_text("test fixture, not a real USD asset")
        manifest = self.root / "MANIFEST.json"
        benchmark.write_json(manifest, {"files": [dict(path="asset.usd", bytes=payload.stat().st_size,
                                                        sha256=benchmark.sha256(payload))]})
        lock = {"bundle_manifest_sha256": benchmark.sha256(manifest)}
        self.assertEqual(benchmark.verify_bundle(self.root, lock)["files_checked"], 1)
        payload.write_text("changed")
        with self.assertRaisesRegex(ValueError, "content changed"):
            benchmark.verify_bundle(self.root, lock)
        with self.assertRaisesRegex(ValueError, "external"):
            benchmark.bundle_path(self.root, "../outside")

    def test_zero_success_is_a_passed_negative_check(self):
        self.episodes(self.root)
        result = benchmark.collect_result(self.root, self.case, 11)
        self.assertTrue(result["expectation_met"])
        self.assertEqual(result["success_rate"], 0.0)

    def test_parallel_overshoot_counts_all_completed_episodes(self):
        self.episodes(self.root, (True, False, False))
        result = benchmark.collect_result(self.root, self.case, 11)
        self.assertEqual(result["completed_episodes"], 3)
        self.assertAlmostEqual(result["success_rate"], 1 / 3)
        self.assertFalse(result["expectation_met"])

    def test_incomplete_rollout_and_missing_report_are_errors(self):
        native = self.episodes(self.root, (False,))
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            benchmark.collect_result(self.root, self.case, 11)
        single = {**self.case, "num_episodes": 1}
        (native / "index.html").unlink()
        with self.assertRaisesRegex(ValueError, "report"):
            benchmark.collect_result(self.root, single, 11)

    def test_wrong_seed_and_duplicate_rows_are_rejected(self):
        native = self.episodes(self.root, seed=22)
        with self.assertRaisesRegex(ValueError, "seed"):
            benchmark.collect_result(self.root, self.case, 11)
        path = native / "episode_results_rank0.jsonl"
        first = json.loads(path.read_text().splitlines()[0])
        first["seed"] = 11
        path.write_text((json.dumps(first) + "\n") * 2)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            benchmark.collect_result(self.root, self.case, 11)

    def test_process_failure_stops_suite_and_preserves_log(self):
        output = self.root / "results"
        runs = [dict(name="first", command=["fake"], case=self.case, seed=11),
                dict(name="second", command=["fake"], case=self.case, seed=11)]
        def failed(command, stdout, **kwargs):
            stdout.write("runtime failure evidence")
            return subprocess.CompletedProcess(command, -9)
        with patch.object(benchmark.subprocess, "run", side_effect=failed) as process:
            self.assertFalse(benchmark.execute_plan(runs, output, {}))
        self.assertEqual(process.call_count, 1)
        self.assertIn("failure evidence", (output / "first.log").read_text())
        result = benchmark.read_json(output / "benchmark_result.json")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["runs"][0]["returncode"], -9)

    def test_zero_exit_with_incomplete_artifacts_cannot_pass(self):
        output = self.root / "results"
        run = dict(name="smoke", command=["fake"], case=self.case, seed=11)
        with patch.object(benchmark.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)):
            self.assertFalse(benchmark.execute_plan([run], output, {}))
        result = benchmark.read_json(output / "benchmark_result.json")
        self.assertEqual(result["runs"][0]["status"], "failed")

    def test_successful_orchestration_and_existing_output_protection(self):
        output = self.root / "results"
        run = dict(name="smoke", command=["fake"], case=self.case, seed=11)
        def complete(command, **kwargs):
            self.episodes(output / "smoke")
            return subprocess.CompletedProcess(command, 0)
        with patch.object(benchmark.subprocess, "run", side_effect=complete):
            self.assertTrue(benchmark.execute_plan([run], output, {}))
        result = benchmark.read_json(output / "benchmark_result.json")
        self.assertEqual(result["runs"][0]["metrics"]["failures"], 2)
        with self.assertRaises(FileExistsError):
            benchmark.execute_plan([run], output, {})


class TaskApiTests(unittest.TestCase):
    def load_overlay(self, typed):
        modules = {}
        for name in ("openarm_arena", "isaaclab_arena", "isaaclab_arena.tasks",
                     "isaaclab_arena.progress_tracking"):
            module = types.ModuleType(name)
            module.__path__ = []
            modules[name] = module
        delivered = types.ModuleType("openarm_arena.environment")
        class Task:
            def __init__(self, source, episode_length_s=90.0, replay_fixture=None):
                self.source = source
                self.episode_length_s = episode_length_s
                self.replay_fixture = replay_fixture
        class Environment:
            pass
        delivered.OpenArmPickPlaceTask = Task
        delivered.OpenArmPickPlaceEnvironment = Environment
        modules[delivered.__name__] = delivered
        if typed:
            termination = types.ModuleType("isaaclab_arena.tasks.task_termination_cfg")
            @dataclass
            class Termination:
                timeout_s: float
                success: list
                failures: dict
            termination.TaskTerminationCfg = Termination
            modules[termination.__name__] = termination
            progress = types.ModuleType("isaaclab_arena.progress_tracking.progress_objective")
            @dataclass
            class Objective:
                name: str
                predicate_sequence: list
            progress.ProgressObjective = Objective
            modules[progress.__name__] = progress
        spec = importlib.util.spec_from_file_location("tested_environment", ROOT / "openarm_benchmark/environment.py")
        overlay = importlib.util.module_from_spec(spec)
        context = patch.dict(sys.modules, modules)
        context.start()
        self.addCleanup(context.stop)
        spec.loader.exec_module(overlay)
        terms = types.SimpleNamespace(success=object(), cube_dropped=object())
        terms.copy = lambda: copy.copy(terms)
        return overlay, types.SimpleNamespace(terminations=terms)

    def test_current_api_preserves_original_predicates_and_explicit_timeout(self):
        overlay, source = self.load_overlay(typed=True)
        cfg = overlay.OpenArmBenchmarkTask(source, episode_length_s=90).get_termination_cfg()
        self.assertEqual(cfg.timeout_s, 90)
        self.assertEqual(len(cfg.success), 1)
        self.assertIs(cfg.success[0].predicate_sequence[0], source.terminations.success)
        self.assertIs(cfg.failures["cube_dropped"], source.terminations.cube_dropped)

    def test_delivery_api_retains_original_termination_terms(self):
        overlay, source = self.load_overlay(typed=False)
        cfg = overlay.OpenArmBenchmarkTask(source).get_termination_cfg()
        self.assertIs(cfg.success, source.terminations.success)
        self.assertIs(cfg.cube_dropped, source.terminations.cube_dropped)


if __name__ == "__main__":
    unittest.main()
