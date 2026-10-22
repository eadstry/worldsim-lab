# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Copyright (c) 2022-2026, The Isaac Lab Project Developers (https://github.com/isaac-sim/IsaacLab/blob/main/CONTRIBUTORS.md).
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""Common prop paths; scene layouts select their own tabletop assets."""

from pathlib import Path

OPENARM_PROJECT_DIR = Path(__file__).resolve().parents[3]
PROP_ASSET_DIR = OPENARM_PROJECT_DIR / "assets"
BLUE_CUBE_USD_PATH = PROP_ASSET_DIR / "blue_cube/blue_cube.usd"
NIGHTSTAND_USD_PATH = PROP_ASSET_DIR / "nightstand/nightstand_fixed.usda"


def validate_prop_assets(scene_assets: tuple[Path, ...] = ()) -> None:
    """Check common props and the assets required by the selected scene.

    Args:
        scene_assets: Files required by the chosen tabletop scene.
    """
    for asset_path in (BLUE_CUBE_USD_PATH, NIGHTSTAND_USD_PATH, *scene_assets):
        assert asset_path.is_file(), f"OpenArm task prop asset not found: {asset_path}"
