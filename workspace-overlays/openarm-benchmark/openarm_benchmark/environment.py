# Copyright (c) 2026. SPDX-License-Identifier: Apache-2.0
"""Reuse the delivered OpenArm scene and predicates with Arena's task API."""

from openarm_arena.environment import OpenArmPickPlaceEnvironment, OpenArmPickPlaceTask


def configure_simulation(cfg, source):
    """Copy source timing while retaining Arena's resolved physics backend."""
    physics = getattr(cfg.sim, "physics", None)
    cfg.sim = source.sim.copy()
    if hasattr(cfg.sim, "physics") and cfg.sim.physics is None:
        cfg.sim.physics = physics
    cfg.decimation = source.decimation
    from openarm_benchmark.recording import configure_native_recorder

    cfg = configure_native_recorder(cfg)
    return cfg


class OpenArmBenchmarkTask(OpenArmPickPlaceTask):
    """Preserve the placement predicate across the two recorded Arena versions."""

    def get_termination_cfg(self):
        source = self.source.terminations.copy()
        try:
            from isaaclab_arena.tasks.task_termination_cfg import TaskTerminationCfg
        except ModuleNotFoundError as error:
            if error.name != "isaaclab_arena.tasks.task_termination_cfg":
                raise
            # The original delivery's Arena revision consumes Isaac Lab terms directly.
            return source

        from isaaclab_arena.progress_tracking.progress_objective import ProgressObjective

        return TaskTerminationCfg(
            timeout_s=self.episode_length_s,
            success=[ProgressObjective(name="place_on_pad", predicate_sequence=[source.success])],
            failures={"cube_dropped": source.cube_dropped},
        )


class OpenArmBenchmarkEnvironment(OpenArmPickPlaceEnvironment):
    """Keep source scene, resets, cameras, controls, and simulation settings."""

    name = "openarm_left_pick_place_benchmark"

    def get_env(self, args_cli):
        from openarm_benchmark.actions import CompatibleGripperAction

        environment = super().get_env(args_cli)
        original = environment.task
        environment.task = OpenArmBenchmarkTask(
            original.source,
            episode_length_s=original.episode_length_s,
            replay_fixture=original.replay_fixture,
        )
        environment.env_cfg_callback = lambda cfg: configure_simulation(cfg, original.source)
        environment.embodiment.action_config.left_gripper_action.class_type = CompatibleGripperAction
        return environment
