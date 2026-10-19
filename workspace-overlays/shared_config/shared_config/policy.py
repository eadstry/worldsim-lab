# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Example policy interfaces; no trained checkpoint is included."""
from __future__ import annotations

from dataclasses import dataclass

import gymnasium as gym
import torch
from isaaclab_arena.assets.register import register_policy
from isaaclab_arena.policy.policy_base import PolicyBase, PolicyCfg



@dataclass
class OpenArmTorchScriptCfg(PolicyCfg):
    """Configure a model accepting the documented observation dictionary."""

    checkpoint: str
    device: str = "cuda:0"


@register_policy
class OpenArmTorchScriptPolicy(PolicyBase[OpenArmTorchScriptCfg]):
    """Evaluate a TorchScript model returning normalized relative-IK actions."""

    name = "openarm_torchscript"

    def __init__(self, config: OpenArmTorchScriptCfg):
        super().__init__(config)
        self.model = torch.jit.load(config.checkpoint, map_location=config.device).eval()

    def get_action(self, env: gym.Env, observation: dict[str, dict[str, torch.Tensor]]) -> torch.Tensor:
        """Run the model without implicit observation normalization or action scaling."""
        inputs = {key: value.to(self.config.device) for key, value in observation["policy"].items()}
        actions = self.model(inputs)
        assert isinstance(actions, torch.Tensor), "The model must return one action tensor"
        assert tuple(actions.shape) == tuple(env.action_space.shape), "Expected [num_envs, 7] actions"
        assert torch.isfinite(actions).all(), "The model produced non-finite actions"
        return actions.to(env.unwrapped.device)
