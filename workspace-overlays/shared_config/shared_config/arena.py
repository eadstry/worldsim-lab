# Copyright (c) 2026, The Isaac Lab Arena Project Developers (https://github.com/isaac-sim/IsaacLab-Arena/blob/main/CONTRIBUTORS.md).
# All rights reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Adapt the delivered OpenArm task to the current Arena termination interface."""

import torch

from isaaclab.envs.mdp.actions.binary_joint_actions import BinaryJointPositionAction
from isaaclab_physx.physics import PhysxCfg
from isaaclab_arena.progress_tracking.progress_objective import ProgressObjective
from isaaclab_arena.tasks.task_termination_cfg import TaskTerminationCfg

from shared_config.arena_base import OpenArmPickPlaceEnvironment, OpenArmPickPlaceTask
from openarm_autodata.shared.envs.actions import RateLimitedBinaryJointPositionAction


class CompatibleGripperAction(RateLimitedBinaryJointPositionAction):
    """Preserve the source gripper rate limit and negative-close convention."""

    def __init__(self, cfg, env):
        BinaryJointPositionAction.__init__(self, cfg, env)
        # Current BinaryJointAction stores Warp indices, unsuitable for Torch indexing.
        self._joint_ids, _ = self._asset.find_joints(cfg.joint_names)
        self._max_position_step = cfg.max_velocity * env.physics_dt
        self._applied_targets = self._asset.data.default_joint_pos.torch[:, self._joint_ids].clone()

    def process_actions(self, actions):
        """Map negative commands to closed and nonnegative commands to open."""
        self._raw_actions[:] = actions
        self._processed_actions = torch.where(actions < 0, self._close_command, self._open_command)
        if self.cfg.clip is not None:
            self._processed_actions = torch.clamp(
                self._processed_actions, min=self._clip[:, :, 0], max=self._clip[:, :, 1]
            )


class CompatibleOpenArmTask(OpenArmPickPlaceTask):
    """Preserve the source placement predicate, failure rule, and evaluation horizon."""

    def get_termination_cfg(self) -> TaskTerminationCfg:
        """Declare the original placement predicate as a single success objective."""
        return TaskTerminationCfg(
            timeout_s=self.episode_length_s,
            success=[
                ProgressObjective(
                    name="place_cube_on_pad",
                    predicate_sequence=[self.source.terminations.success.copy()],
                )
            ],
            failures={"cube_dropped": self.source.terminations.cube_dropped.copy()},
        )


class CompatibleOpenArmEnvironment(OpenArmPickPlaceEnvironment):
    """Load the delivery with a current Arena task adapter."""

    def get_env(self, args_cli):
        """Compose the delivery and replace its task with the compatible adapter."""
        description = super().get_env(args_cli)
        original = description.task
        description.task = CompatibleOpenArmTask(
            original.source,
            episode_length_s=original.episode_length_s,
            replay_fixture=original.replay_fixture,
        )
        description.embodiment.action_config.left_gripper_action.class_type = CompatibleGripperAction

        def configure_simulation(cfg):
            assert isinstance(cfg.sim.physics, PhysxCfg), "The OpenArm delivery requires PhysX."
            device = cfg.sim.device
            cfg.sim = original.source.sim.copy()
            # The source uses physics=None, which Isaac Lab interprets as default PhysX.
            # Current Arena requires an explicit backend config after the callback.
            if cfg.sim.physics is None:
                cfg.sim.physics = PhysxCfg()
            cfg.sim.device = device
            cfg.decimation = original.source.decimation
            return cfg

        description.env_cfg_callback = configure_simulation
        return description
