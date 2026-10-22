# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared cuRobo robot-model loading for OpenArm; no task obstacle policy."""

from pathlib import Path

from curobo.geom.types import WorldConfig

from autodata_interfaces.motion_planners.curobo.curobo_planner_cfg import CuroboPlannerCfg

ROBOT_CONFIG = Path(__file__).resolve().parent / "autodata_configs/planners/openarm_right.yml"


class OpenArmRightPlannerCfg(CuroboPlannerCfg):
    """Use the OpenArm kinematic model and the obstacles extracted from the live scene."""

    def get_robot_config(self) -> dict:
        """Resolve bundled robot assets relative to this package."""
        robot_config = super().get_robot_config()
        kinematics = robot_config["kinematics"]
        for key in ("urdf_path", "asset_root_path"):
            kinematics[key] = str((ROBOT_CONFIG.parent / kinematics[key]).resolve())
        return robot_config

    def get_world_config(self) -> WorldConfig:
        """Start with an empty world; the planner imports the task's USD obstacles."""
        return WorldConfig()
