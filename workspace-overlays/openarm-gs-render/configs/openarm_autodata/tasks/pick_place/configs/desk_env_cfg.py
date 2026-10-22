# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mesh-desk variants using the standard Isaac Lab environment-config registry."""

from isaaclab.utils.configclass import configclass

from .env_cfg import OpenArmBimanualPickPlaceEnvCfg
from .ker_env_cfg import OpenArmKerLeftPickPlaceEnvCfg, OpenArmKerPickPlaceEnvCfg
from .left_env_cfg import OpenArmLeftPickPlaceEnvCfg


@configclass
class OpenArmDeskPickPlaceEnvCfg(OpenArmBimanualPickPlaceEnvCfg):
    """Use the mesh-desk layout with the inherited robot and task configuration."""

    scene_name: str = "desk"


@configclass
class OpenArmDeskLeftPickPlaceEnvCfg(OpenArmLeftPickPlaceEnvCfg):
    """Use the mesh-desk layout with the inherited robot and task configuration."""

    scene_name: str = "desk"


@configclass
class OpenArmDeskKerPickPlaceEnvCfg(OpenArmKerPickPlaceEnvCfg):
    """Use the mesh-desk layout with the inherited robot and task configuration."""

    scene_name: str = "desk"


@configclass
class OpenArmDeskKerLeftPickPlaceEnvCfg(OpenArmKerLeftPickPlaceEnvCfg):
    """Use the mesh-desk layout with the inherited robot and task configuration."""

    scene_name: str = "desk"
