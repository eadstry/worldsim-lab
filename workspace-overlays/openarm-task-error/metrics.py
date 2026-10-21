# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Host-only metrics for complete-task trials, retaining failures and phase coverage."""
from __future__ import annotations

import numpy as np

PHASES = ('approach', 'grasp_lift', 'transport', 'release_settle')


def summarize(arrays: dict, control_dt: float) -> dict:
    """Summarize one trial; joint actions and state have identical angle semantics."""
    result = {}
    for name, x, y in [('request_pre', 'request', 'pre'), ('request_post', 'request', 'post'),
                       ('request_applied', 'request', 'applied'), ('applied_post', 'applied', 'post')]:
        d = np.abs(arrays[x][:, :7] - arrays[y][:, :7]) * 180 / np.pi
        result[name] = {'mae_deg': float(d.mean()), 'p95_deg': float(np.quantile(d, .95)),
                        'per_joint_mae_deg': d.mean(0).tolist()}
    error = np.abs(arrays['request'][:, :7] - arrays['pre'][:, :7]) * 180 / np.pi
    result['phases'] = {}
    for phase, label in enumerate(PHASES):
        mask = arrays['phase'] == phase
        result['phases'][label] = {'frames': int(mask.sum()),
                                  'mae_deg': float(error[mask].mean()) if mask.any() else None}
    result['frames'] = len(error)
    result['duration_s'] = len(error) * control_dt
    result['ee_tracking_p95_mm'] = float(np.quantile(arrays['ee_error_m'], .95) * 1000)
    return result


def stable_success(raw_success, lifted, fingers, consecutive, required_frames):
    """Require prior lifting, both fingers open, and uninterrupted placement success."""
    valid = np.asarray(raw_success, bool) & lifted & (np.asarray(fingers).min(-1) >= .3)
    count = np.where(valid, consecutive + 1, 0)
    return count, count >= required_frames
