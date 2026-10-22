# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Copyright (c) 2022-2026, The Isaac Lab Project Developers (https://github.com/isaac-sim/IsaacLab/blob/main/CONTRIBUTORS.md).
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""Scene configuration for bimanual OpenArm cube pick-and-place."""

import isaaclab.sim as sim_utils
from isaaclab.assets import ArticulationCfg, AssetBaseCfg, RigidObjectCfg
from isaaclab.scene import InteractiveSceneCfg
from isaaclab.utils.configclass import configclass

from openarm_autodata.shared.configs.robot_v2_cfg import OPENARM_V2_CFG

from .prop_assets import BLUE_CUBE_USD_PATH, NIGHTSTAND_USD_PATH


@configclass
class OpenArmBimanualSceneCfg(InteractiveSceneCfg):
    """Shared scene entities; the environment config applies the selected layout."""

    ground = AssetBaseCfg(
        prim_path="/World/GroundPlane",
        spawn=sim_utils.GroundPlaneCfg(),
    )

    nightstand = AssetBaseCfg(
        prim_path="{ENV_REGEX_NS}/Nightstand",
        spawn=sim_utils.UsdFileCfg(usd_path=str(NIGHTSTAND_USD_PATH)),
        init_state=AssetBaseCfg.InitialStateCfg(),
    )

    table = RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/Table",
        spawn=sim_utils.UsdFileCfg(
            usd_path="",  # Filled from the selected scene YAML before environment creation.
            rigid_props=sim_utils.RigidBodyPropertiesCfg(
                rigid_body_enabled=True,
                kinematic_enabled=True,
                disable_gravity=True,
            ),
        ),
        init_state=RigidObjectCfg.InitialStateCfg(),
    )

    mousepad: RigidObjectCfg | None = None
    """Optional pad; rigid-body properties are authored in the selected USD."""

    cube = RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/Cube",
        spawn=sim_utils.UsdFileCfg(
            usd_path=str(BLUE_CUBE_USD_PATH),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(
                rigid_body_enabled=True,
                kinematic_enabled=False,
                disable_gravity=False,
                max_depenetration_velocity=1.0,
            ),
            mass_props=sim_utils.MassPropertiesCfg(mass=0.04),
            collision_props=sim_utils.CollisionPropertiesCfg(
                collision_enabled=True,
                contact_offset=0.002,
                rest_offset=0.0,
            ),
            physics_material=sim_utils.RigidBodyMaterialCfg(
                static_friction=1.2,
                dynamic_friction=1.0,
                restitution=0.0,
            ),
        ),
        init_state=RigidObjectCfg.InitialStateCfg(),
    )

    robot: ArticulationCfg = OPENARM_V2_CFG.replace(
        prim_path="{ENV_REGEX_NS}/Robot",
        init_state=OPENARM_V2_CFG.init_state.copy(),
    )

    dome_light = AssetBaseCfg(
        prim_path="/World/DomeLight",
        spawn=sim_utils.DomeLightCfg(intensity=1800.0, color=(1.0, 1.0, 1.0)),
    )
