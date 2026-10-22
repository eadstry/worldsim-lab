# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Copyright (c) 2026, The Isaac Lab Project Developers (https://github.com/isaac-sim/IsaacLab/blob/main/CONTRIBUTORS.md).
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""Isaac Lab configuration for the project-local OpenArm v2.0 bimanual robot."""

from pathlib import Path

import isaaclab.sim as sim_utils
from isaaclab.actuators import ImplicitActuatorCfg
from isaaclab.assets import ArticulationCfg

OPENARM_V2_PROJECT_DIR = Path(__file__).resolve().parents[2]
OPENARM_V2_USD_PATH = OPENARM_V2_PROJECT_DIR / "assets/openarm_v2/usd/openarm_v20_bimanual/openarm_v20_bimanual.usda"

OPENARM_V2_LEFT_ARM_JOINT_NAMES = tuple(f"openarm_left_joint{index}" for index in range(1, 8))
OPENARM_V2_RIGHT_ARM_JOINT_NAMES = tuple(f"openarm_right_joint{index}" for index in range(1, 8))
OPENARM_V2_LEFT_FINGER_JOINT_NAMES = (
    "openarm_left_finger_joint1",
    "openarm_left_finger_joint2",
)
OPENARM_V2_RIGHT_FINGER_JOINT_NAMES = (
    "openarm_right_finger_joint1",
    "openarm_right_finger_joint2",
)
OPENARM_V2_LEFT_EE_BODY_NAME = "openarm_left_ee_base_link"
OPENARM_V2_RIGHT_EE_BODY_NAME = "openarm_right_ee_base_link"
OPENARM_V2_LEFT_GRASP_FRAME_NAME = "openarm_left_grasp_frame"
OPENARM_V2_RIGHT_GRASP_FRAME_NAME = "openarm_right_grasp_frame"
OPENARM_V2_ROOT_BODY_REL_PATH = "Geometry/world/openarm_body_link0"
OPENARM_V2_RIGHT_EE_BODY_REL_PATH = (
    f"{OPENARM_V2_ROOT_BODY_REL_PATH}/openarm_right_base_link/openarm_right_link1/openarm_right_link2/"
    "openarm_right_link3/openarm_right_link4/openarm_right_link5/openarm_right_link6/"
    "openarm_right_ee_base_link"
)
OPENARM_V2_GRASP_FRAME_OFFSET_POS = (-0.00143, 0.0, -0.138)
OPENARM_V2_GRASP_FRAME_OFFSET_ROT = (0.0, 0.70710678, 0.0, 0.70710678)

OPENARM_V2_LEFT_GRIPPER_OPEN_POSITION = 0.70
OPENARM_V2_RIGHT_GRIPPER_OPEN_POSITION = -0.70
OPENARM_V2_GRIPPER_CLOSED_POSITION = 0.0


def make_openarm_v2_cfg() -> ArticulationCfg:
    """Create the complete OpenArm v2.0 bimanual articulation configuration."""
    if not OPENARM_V2_USD_PATH.is_file():
        raise FileNotFoundError(f"OpenArm v2.0 USD does not exist: {OPENARM_V2_USD_PATH}")

    return ArticulationCfg(
        spawn=sim_utils.UsdFileCfg(
            usd_path=str(OPENARM_V2_USD_PATH),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(
                max_depenetration_velocity=1.0,
            ),
            articulation_props=sim_utils.ArticulationRootPropertiesCfg(
                solver_position_iteration_count=16,
                solver_velocity_iteration_count=4,
            ),
        ),
        articulation_root_prim_path="/Geometry/world",
        init_state=ArticulationCfg.InitialStateCfg(
            joint_pos={
                "openarm_left_joint[1-3]": 0.0,
                "openarm_left_joint4": 1.20,
                "openarm_left_joint[5-7]": 0.0,
                "openarm_right_joint[1-3]": 0.0,
                "openarm_right_joint4": 1.20,
                "openarm_right_joint[5-7]": 0.0,
                "openarm_left_finger_joint[1-2]": OPENARM_V2_LEFT_GRIPPER_OPEN_POSITION,
                "openarm_right_finger_joint[1-2]": OPENARM_V2_RIGHT_GRIPPER_OPEN_POSITION,
            },
            joint_vel={".*": 0.0},
        ),
        actuators={
            "arms": ImplicitActuatorCfg(
                joint_names_expr=[
                    "openarm_left_joint[1-7]",
                    "openarm_right_joint[1-7]",
                ],
                velocity_limit_sim={
                    "openarm_(left|right)_joint[1-4]": 2.175,
                    "openarm_(left|right)_joint[5-7]": 2.61,
                },
                effort_limit_sim={
                    "openarm_(left|right)_joint[1-2]": 40.0,
                    "openarm_(left|right)_joint[3-4]": 27.0,
                    "openarm_(left|right)_joint[5-7]": 7.0,
                },
                # 保留原机械臂增益供对照；运行时由此处配置写入，不再写入 USD。
                # stiffness=400.0,
                # damping=80.0,
                stiffness={
                    "openarm_(left|right)_joint[1-3]": 370.0,
                    "openarm_(left|right)_joint4": 360.0,
                    "openarm_(left|right)_joint[5-7]": 310.0,
                },
                damping={
                    "openarm_(left|right)_joint1": 32.75,
                    "openarm_(left|right)_joint2": 32.5,
                    "openarm_(left|right)_joint[3-4]": 32.0,
                    "openarm_(left|right)_joint5": 30.7,
                    "openarm_(left|right)_joint6": 30.6,
                    "openarm_(left|right)_joint7": 30.5,
                },
            ),
            "grippers": ImplicitActuatorCfg(
                joint_names_expr=[
                    "openarm_left_finger_joint[1-2]",
                    "openarm_right_finger_joint[1-2]",
                ],
                velocity_limit_sim=5.0,
                effort_limit_sim=7.0,
                stiffness=400.0,
                damping=40.0,
            ),
        },
        soft_joint_pos_limit_factor=0.95,
    )


OPENARM_V2_CFG = make_openarm_v2_cfg()
"""Complete OpenArm v2.0 bimanual configuration for PhysX simulation."""
