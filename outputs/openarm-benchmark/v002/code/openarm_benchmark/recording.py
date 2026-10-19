"""Bridge Arena's video option to the current Isaac Lab native recorder."""

import dataclasses
import json
import math
import os
from pathlib import Path


def associate_single_episode_video(directory):
    """Name a single env-0 episode clip so Arena's report can associate it."""
    directory = Path(directory)
    clips = list(directory.glob("arena-viewport_*.mp4"))
    rows = [
        json.loads(line)
        for path in directory.glob("episode_results_rank*.jsonl")
        for line in path.read_text().splitlines()
        if line.strip()
    ]
    env_zero = [row for row in rows if row.get("env_id") == 0]
    # A clip spanning several episodes must not be attached to one episode.
    if len(clips) != 1 or len(env_zero) != 1:
        return None
    target = directory / f"arena-native-env0-viewport-episode-{env_zero[0]['episode_in_env']}.mp4"
    if target.exists():
        raise FileExistsError(target)
    clips[0].rename(target)
    return target


def install_native_recording(arena_root, arguments):
    """Select native step-driven capture only for the recorded current Arena API."""
    arguments = list(arguments)
    if "--record_viewport_video" not in arguments or not (
        arena_root / "isaaclab_arena/tasks/task_termination_cfg.py"
    ).is_file():
        return arguments

    from isaaclab_arena.video import video_recording

    timestamped_run_dir = video_recording.timestamped_run_dir
    wrap_env_for_video = video_recording.wrap_env_for_video

    def remember_output_directory(base_dir):
        directory = timestamped_run_dir(base_dir)
        os.environ["OPENARM_ARENA_VIDEO_DIRECTORY"] = directory
        return directory

    def use_native_viewport(env, config, num_steps, num_episodes):
        # Current Isaac Lab render(rgb_array) returns None; its internal recorder
        # captures the same live rollout directly after env.step().
        config = dataclasses.replace(config, record_viewport_video=False)
        env = wrap_env_for_video(env, config, num_steps, num_episodes)
        import gymnasium as gym

        class ReportVideoWrapper(gym.Wrapper):
            def close(self):
                self.env.close()
                associate_single_episode_video(os.environ["OPENARM_ARENA_VIDEO_DIRECTORY"])

        return ReportVideoWrapper(env)

    video_recording.timestamped_run_dir = remember_output_directory
    video_recording.wrap_env_for_video = use_native_viewport
    os.environ["OPENARM_ARENA_NATIVE_RECORDING"] = "1"
    os.environ["OPENARM_ARENA_VIDEO_EPISODES"] = arguments[arguments.index("--num_episodes") + 1]
    viz_index = arguments.index("--viz") + 1
    if arguments[viz_index] == "none":
        arguments[viz_index] = "kit"
        os.environ["HEADLESS"] = "1"
    print("OpenArm: live Arena rollout capture via Isaac Lab VideoRecorderCfg / Kit", flush=True)
    return arguments


def configure_native_recorder(cfg):
    """Add a live viewport stream without changing task observations or physics."""
    if os.environ.get("OPENARM_ARENA_NATIVE_RECORDING") != "1":
        return cfg
    from isaaclab.envs.utils.video_recorder_cfg import VideoRecorderCfg

    steps_per_episode = math.ceil(cfg.episode_length_s / (cfg.sim.dt * cfg.decimation))
    cfg.video_recorders = [
        VideoRecorderCfg(
            source="visualizer:kit",
            output_dir=os.environ["OPENARM_ARENA_VIDEO_DIRECTORY"],
            video_length=steps_per_episode * int(os.environ["OPENARM_ARENA_VIDEO_EPISODES"]),
            output_filename_prefix="arena-viewport",
        )
    ]
    return cfg
