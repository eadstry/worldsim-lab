# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Convert the OpenArm v1 robot dictionary without changing the shared source."""
from __future__ import annotations

from copy import deepcopy


def convert_robot(robot: dict) -> dict:
    """Preserve authored geometry and joint ordering while renaming v2 model fields."""
    result = deepcopy(robot)
    kin = result['kinematics']
    kin['tool_frames'] = [kin.pop('ee_link')]
    cspace = kin['cspace']
    cspace['default_joint_position'] = cspace.pop('retract_config')
    return result
