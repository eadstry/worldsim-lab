# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Expose the original OpenArm left-arm scene and success rule to Arena."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import torch
from isaaclab.envs import ManagerBasedRLEnv
from isaaclab.envs.common import ViewerCfg
from isaaclab.managers import EventTermCfg
from isaaclab_arena.embodiments.common.arm_mode import ArmMode
from isaaclab_arena.embodiments.embodiment_base import EmbodimentBase
from isaaclab_arena.environments.isaaclab_arena_environment import IsaacLabArenaEnvironment
from isaaclab_arena.metrics.metric_base import MetricBase
from isaaclab_arena.metrics.success_rate import SuccessRateMetric
from isaaclab_arena.scene.scene import Scene
from isaaclab_arena.tasks.task_base import TaskBase
from isaaclab_arena.utils.configclass import make_configclass
from isaaclab_arena_environments.example_environment_base import ExampleEnvironmentBase

from openarm_autodata.tasks.pick_place.configs.left_env_cfg import OpenArmLeftPickPlaceEnvCfg
from shared_config.runtime import make_env_cfg

LANGUAGE_INSTRUCTION = (
    "Pick up the blue cube with the left arm, place it fully on the scanned mouse pad, " "release it and let it settle."
)


def _scene_subset(scene: object, names: tuple[str, ...], class_name: str) -> object:
    fields = [(name, type(getattr(scene, name)), getattr(scene, name).copy()) for name in names]
    return make_configclass(class_name, fields)()


def restore_fixture_state(env: ManagerBasedRLEnv, env_ids: torch.Tensor, fixture_path: str) -> None:
    """Restore a regression episode state relative to each environment origin."""
    state = {}
    with np.load(fixture_path, allow_pickle=False) as fixture:
        for key in fixture.files:
            if not key.startswith("initial_state/"):
                continue
            value = torch.as_tensor(fixture[key], device=env.device)
            assert value.shape[0] == 1, "Regression fixtures must contain one initial state"
            value = value.expand(len(env_ids), *value.shape[1:]).clone()
            fields = key.split("/")[1:]
            node = state
            for field in fields[:-1]:
                node = node.setdefault(field, {})
            node[fields[-1]] = value
    env.scene.reset_to(state, env_ids=env_ids, is_relative=True)


class OpenArmLeftEmbodiment(EmbodimentBase):
    """Provide the source robot, TCP, calibrated cameras, actions, and observations."""

    name = "openarm_left_ik"
    default_arm_mode = ArmMode.LEFT

    def __init__(self, source: OpenArmLeftPickPlaceEnvCfg):
        super().__init__(enable_cameras=True, arm_mode=ArmMode.LEFT)
        self.scene_config = _scene_subset(
            source.scene,
            ("robot", "ee_frame", "left_hand_camera", "right_hand_camera", "third_person_camera"),
            "OpenArmRobotSceneCfg",
        )
        self.action_config = source.actions.copy()
        self.observation_config = source.observations.copy()


class OpenArmPickPlaceTask(TaskBase):
    """Reuse source resets and success criteria with an explicit evaluation horizon."""

    def __init__(
        self,
        source: OpenArmLeftPickPlaceEnvCfg,
        episode_length_s: float = 90.0,
        replay_fixture: str | None = None,
    ):
        assert episode_length_s > 0, "Evaluation episode length must be positive"
        super().__init__(episode_length_s=episode_length_s, task_description=LANGUAGE_INSTRUCTION)
        self.source = source
        self.replay_fixture = replay_fixture

    def get_scene_cfg(self) -> object:
        """Return original task props and lighting."""
        return _scene_subset(
            self.source.scene,
            ("ground", "nightstand", "table", "cube", "dome_light"),
            "OpenArmPropsSceneCfg",
        )

    def get_termination_cfg(self) -> object:
        """Return original timeout, dropped-cube, and placement success conditions."""
        return self.source.terminations.copy()

    def get_events_cfg(self) -> object:
        """Return randomized source resets or an explicitly selected regression reset."""
        if self.replay_fixture is None:
            return self.source.events.copy()
        fixture_path = str(Path(self.replay_fixture).resolve())
        assert Path(fixture_path).is_file(), f"Fixture does not exist: {fixture_path}"
        return make_configclass(
            "OpenArmRegressionEventsCfg",
            [
                ("reset_all", EventTermCfg, self.source.events.reset_all.copy()),
                (
                    "restore_fixture",
                    EventTermCfg,
                    EventTermCfg(
                        func=restore_fixture_state,
                        mode="reset",
                        params={"fixture_path": fixture_path},
                    ),
                ),
            ],
        )()

    def get_metrics(self) -> list[MetricBase]:
        """Record Arena's native episode success-rate metric."""
        return [SuccessRateMetric()]

    def get_mimic_env_cfg(self, arm_mode: ArmMode) -> object:
        """Reject data-generation-only Mimic mode for this evaluation adapter."""
        raise NotImplementedError("This delivery provides Arena policy evaluation, not Mimic generation")

    def get_viewer_cfg(self) -> ViewerCfg:
        """Return a view of the tabletop workspace."""
        return ViewerCfg(eye=(2.0, 1.6, 2.0), lookat=(0.5, 0.2, 1.05))


class OpenArmPickPlaceEnvironment(ExampleEnvironmentBase):
    """Load the task through Arena's external-environment CLI."""

    name = "openarm_left_pick_place"

    def get_env(self, args_cli: argparse.Namespace) -> IsaacLabArenaEnvironment:
        """Compose the source OpenArm configuration with Arena evaluation metrics."""
        source = make_env_cfg()
        task = OpenArmPickPlaceTask(
            source,
            episode_length_s=args_cli.openarm_episode_length_s,
            replay_fixture=args_cli.openarm_replay_fixture,
        )

        def configure_simulation(cfg):
            cfg.sim = source.sim.copy()
            cfg.decimation = source.decimation
            return cfg

        return IsaacLabArenaEnvironment(
            name=self.name,
            scene=Scene(assets=[]),
            embodiment=OpenArmLeftEmbodiment(source),
            task=task,
            env_cfg_callback=configure_simulation,
        )

    @staticmethod
    def add_cli_args(parser: argparse.ArgumentParser) -> None:
        """Add task-specific evaluation options."""
        parser.add_argument("--openarm_episode_length_s", type=float, default=90.0)
        parser.add_argument(
            "--openarm_replay_fixture",
            type=str,
            default=None,
            help="Regression only: replace randomized resets with this fixture initial state.",
        )
