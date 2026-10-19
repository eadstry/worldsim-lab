# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Joint-space path retiming shared by the prototype and CPU checks."""
import torch


def resample_path(path: torch.Tensor, step_size: float) -> torch.Tensor:
    """Match the existing v1 overlay's uniform joint-distance retiming [rad]."""
    assert step_size > 0
    if len(path) <= 1:
        return path
    distances = torch.linalg.vector_norm(path[1:] - path[:-1], dim=-1)
    path = path[torch.cat((torch.ones(1, dtype=torch.bool, device=path.device), distances > 1e-6))]
    if len(path) <= 1:
        return path
    distances = torch.linalg.vector_norm(path[1:] - path[:-1], dim=-1)
    cumulative = torch.cat((distances.new_zeros(1), distances.cumsum(0)))
    if cumulative[-1] < 1e-6:
        return path
    samples = torch.linspace(0, cumulative[-1], int(torch.ceil(cumulative[-1] / step_size).item()) + 1,
                             device=path.device)
    indices = torch.searchsorted(cumulative, samples).clamp(1, len(path) - 1)
    weights = ((samples - cumulative[indices - 1]) / (cumulative[indices] - cumulative[indices - 1]))[:, None]
    return torch.lerp(path[indices - 1], path[indices], weights)
