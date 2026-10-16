# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Run the actual AutoData generation entrypoint with the delivered OpenArm package."""

import argparse
import math
import os
import sys
from pathlib import Path

def build_source(source, args):
    if args.debug_planner:
        anchor_debug = "planner_config = CuroboPlannerCfg.from_profile(planner_profile)"
        assert source.count(anchor_debug) == 1
        source = source.replace(anchor_debug, anchor_debug + "\n            planner_config.debug_planner = True", 1)
    anchor = "simulation_app = app_launcher.app"
    assert source.count(anchor) == 1, "Upstream launcher changed; review the integration hook"
    runtime_path = getattr(args, "runtime", None)
    runtime_arg = repr(str(runtime_path)) if runtime_path is not None else "None"
    source = source.replace(anchor, anchor + f"\nfrom compat import install\ninstall(runtime={runtime_arg})", 1)
    policy_anchor = "generation_policy_params = task_descriptor.get_generation_policy()"
    assert source.count(policy_anchor) == 1
    source = source.replace(policy_anchor, policy_anchor + f"""
    generation_policy_params.num_steps_final_hold = {args.final_hold_steps}
    from telemetry import record_policy
    record_policy(generation_policy_params, {args.generation_num_trials}, {args.num_envs})
""", 1)
    counter = '        stats["num_attempts"] += 1'
    assert source.count(counter) == 1, "Upstream attempt accounting changed; review the failure limit"
    source = source.replace(counter, counter + '''
        failure_limit = data_generator.datastream.get_generation_policy().max_num_failures
        if stats["num_failures"] >= failure_limit:
            raise RuntimeError(f"OpenArm generation reached failure limit {failure_limit}")
''', 1)
    background = getattr(args, 'background', None)
    if background is not None:
        anchor_env = "    env = gym.make(env_name, cfg=env_cfg).unwrapped"
        assert source.count(anchor_env) == 1, "Upstream environment hook changed"
        source = source.replace(anchor_env, "    from background import configure_background, verify_background\n"
            + f"    _background = {background!r}\n"
            + "    configure_background(env_cfg, _background)\n" + anchor_env
            + f"\n    verify_background(env, _background, {str(args.output_file.resolve())!r})", 1)
        shutdown = '    simulation_app.close()'
        assert source.count(shutdown) == 1, 'Upstream shutdown hook changed'
        source = source.replace(shutdown, '    from background import annotate_dataset\n'
            + f'    annotate_dataset({str(args.output_file.resolve())!r})\n' + shutdown, 1)
    if args.export_workers:
        import json
        os.environ["OPENARM_ASYNC_EXPORT"] = json.dumps(dict(
            output=str(args.output_file.resolve()), workers=args.export_workers,
            memory_gib=args.export_queue_memory_gib, timeout=args.export_timeout_seconds))
        env_anchor = "    env = gym.make(env_name, cfg=env_cfg).unwrapped"
        assert source.count(env_anchor) == 1
        source = source.replace(env_anchor, """    from async_export import configure, attach
    import json, os
    configure(env_cfg)
""" + env_anchor + """
    attach(env.recorder_manager, json.loads(os.environ['OPENARM_ASYNC_EXPORT']))
""", 1)
        finish_anchor = "        if generation_completed and args_cli.result_file:"
        assert source.count(finish_anchor) == 1
        source = source.replace(finish_anchor, """        if not generation_completed:
            raise RuntimeError('Generation ended before target; async shards retained')
        from async_export import finish
        finish(expected_successes=async_components["stats"]["num_success"])
""" + finish_anchor, 1)
    else:
        os.environ.pop("OPENARM_ASYNC_EXPORT", None)
    close_anchor = "        env.close()"
    assert source.count(close_anchor) == 1
    source = source.replace(close_anchor, close_anchor + """
        if locals().get('generation_completed', False):
            from telemetry import record_output_ready
            record_output_ready()
""", 1)
    return source


def main():
    from export_governor import parse_workers
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--autodata-root", type=Path, default=Path(__file__).resolve().parents[2] / "AutoData")
    parser.add_argument("--runtime", type=Path, default=None,
                        help="Existing prepared OpenArm runtime; read without changing it")
    parser.add_argument("--background-config", type=Path, default=None,
                        help="JSON HDR candidate pool; sampled once per production process")
    parser.add_argument("--background-seed", type=int, default=101)
    parser.add_argument("--arm", choices=("left", "right"), default="right")
    parser.add_argument("--input_file", type=Path, required=True)
    parser.add_argument("--output_file", type=Path, required=True)
    parser.add_argument("--num_envs", type=int, default=1)
    parser.add_argument("--generation_num_trials", type=int, default=1)
    parser.add_argument("--task_descriptor", type=Path, default=None)
    parser.add_argument("--debug-planner", action="store_true")
    parser.add_argument("--final-hold-steps", type=int, default=0)
    parser.add_argument("--log-interval", type=float, default=10)
    parser.add_argument("--export-workers", "--export-max-workers", type=parse_workers, default=0,
                        help="auto: admit save processes using server resources; integer: process cap; 0: synchronous")
    parser.add_argument("--export-queue-memory-gib", type=float, default=16)
    parser.add_argument("--export-timeout-seconds", type=float, default=600)
    args = parser.parse_args()
    assert args.export_workers == 'auto' or args.export_workers >= 0
    assert math.isfinite(args.export_queue_memory_gib) and args.export_queue_memory_gib > 0
    assert math.isfinite(args.export_timeout_seconds) and args.export_timeout_seconds > 0
    if args.export_workers:
        from export_resources import resolve_export_memory_gib
        args.export_queue_memory_gib = resolve_export_memory_gib(args.export_queue_memory_gib)
    root = Path(__file__).resolve().parent
    assert args.input_file.is_file(), f"Missing OpenArm annotated HDF5: {args.input_file}"
    assert args.input_file.resolve() != args.output_file.resolve(), "Input and output must differ"
    assert not args.output_file.exists(), f"Output already exists: {args.output_file}"
    assert args.num_envs > 0 and args.generation_num_trials > 0
    assert args.final_hold_steps >= 0
    assert args.log_interval > 0
    os.environ["OPENARM_TELEMETRY_FILE"] = str(args.output_file.resolve().with_suffix(".telemetry.jsonl"))
    os.environ["OPENARM_LOG_INTERVAL"] = str(args.log_interval)
    runtime = args.runtime.resolve() if args.runtime else root / "runtime"
    args.runtime = runtime
    from background import select_background
    args.background = select_background(args.background_config, args.background_seed)
    if args.background is not None:
        assert not args.output_file.with_suffix('.background.json').exists(), 'Existing background record'
    configs = runtime / "openarm_autodata/tasks/pick_place/autodata_configs"
    script = args.autodata_root.resolve() / "scripts/generate_dataset.py"
    assert script.is_file(), script
    assert configs.is_dir(), "Run prepare.py on the host first"
    # Validate source annotations before paying the cost of starting Isaac Sim.
    import h5py
    import numpy as np

    with h5py.File(args.input_file, "r") as dataset:
        assert "data" in dataset and len(dataset["data"]) > 0, "Source HDF5 has no episodes"
        for episode in dataset["data"].values():
            actions = episode["actions"]
            assert len(actions.shape) == 2 and actions.shape[1] == 7, "Expected OpenArm 7D relative IK actions"
            info = episode["obs/datagen_info"]
            for name in ("eef_pose", "target_eef_pose"):
                assert args.arm in info[name], f"{episode.name}: missing {name}/{args.arm}"
                assert info[name][args.arm].shape == (len(actions), 4, 4)
            for obj in ("cube", "table"):
                assert obj in info["object_pose"], f"{episode.name}: missing object pose {obj}"
            starts = []
            for signal in ("grasp", "place"):
                values = np.asarray(info[f"subtask_start_signals/{signal}"]).reshape(-1)
                assert len(values) == len(actions)
                rises = np.flatnonzero((values[:-1] == 0) & (values[1:] != 0))
                assert len(rises), f"{episode.name}: {signal} has no start transition"
                starts.append(int(rises[0]) + 1)
            terms = np.asarray(info["subtask_term_signals/grasp"]).reshape(-1)
            assert len(terms) == len(actions)
            rises = np.flatnonzero((terms[:-1] == 0) & (terms[1:] != 0))
            assert len(rises), f"{episode.name}: grasp has no termination transition"
            grasp_end = int(rises[0]) + 2
            assert starts[0] < grasp_end < starts[1] < len(actions), f"{episode.name}: invalid skill boundaries"
    print("OpenArm source annotation preflight passed; starting Isaac Sim", flush=True)
    sys.path[:0] = [str(root), str(runtime), str(args.autodata_root.resolve())]
    sys.argv = [
        str(script), "--viz", "none", "--enable_cameras",
        "--kit_args", "--enable omni.usd.schema.omni_lens_distortion",
        "--env_name", f"Isaac-PickPlace-Cube-OpenArm-Bimanual-{args.arm.title()}-IK-Rel-v0",
        "--alg", "skillgen", "--task_descriptor", str(args.task_descriptor.resolve() if args.task_descriptor else configs / f"tasks/openarm_bimanual_{args.arm}_pick_place.yaml"),
        "--embodiment", str(configs / f"embodiments/openarm_bimanual_{args.arm}_ik_rel.yaml"),
        "--env_profile", str(configs / f"env_profiles/openarm_{args.arm}_skillgen.yaml"),
        "--input_file", str(args.input_file.resolve()), "--output_file", str(args.output_file.resolve()),
        "--num_envs", str(args.num_envs), "--generation_num_trials", str(args.generation_num_trials),
        "--result_file", str(args.output_file.resolve().with_suffix(".result.json")),
    ]
    # Insert the registration hook immediately AFTER Isaac Sim starts. No upstream file is edited.
    source = build_source(script.read_text(), args)
    namespace = {"__name__": "__main__", "__file__": str(script)}
    try:
        exec(compile(source, str(script), "exec"), namespace)
    except BaseException:
        from async_export import abort
        abort()
        import traceback
        details = traceback.format_exc()
        args.output_file.with_suffix(".error.txt").write_text(details)
        print(details, file=sys.__stderr__, flush=True)
        raise
    finally:
        from async_export import abort
        abort()
        app = namespace.get("simulation_app")
        if app is not None and app.is_running():
            app.close()


if __name__ == "__main__":
    main()
