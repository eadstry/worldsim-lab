# Copyright (c) 2026. SPDX-License-Identifier: Apache-2.0
"""Reuse the delivered OpenArm scene and predicates with Arena's task API."""

from openarm_arena.environment import OpenArmPickPlaceEnvironment, OpenArmPickPlaceTask


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
        environment = super().get_env(args_cli)
        original = environment.task
        environment.task = OpenArmBenchmarkTask(
            original.source,
            episode_length_s=original.episode_length_s,
            replay_fixture=original.replay_fixture,
        )
        return environment
