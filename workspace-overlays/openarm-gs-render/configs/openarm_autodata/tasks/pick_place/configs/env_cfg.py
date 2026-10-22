# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Copyright (c) 2022-2026, The Isaac Lab Project Developers (https://github.com/isaac-sim/IsaacLab/blob/main/CONTRIBUTORS.md).
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""Standard Isaac Lab environment for bimanual OpenArm cube pick-and-place."""

import isaaclab.sim as sim_utils
from isaaclab.assets import RigidObjectCfg
from isaaclab.controllers import DifferentialIKControllerCfg
from isaaclab.envs import ManagerBasedRLEnvCfg
from isaaclab.envs import mdp as base_mdp
from isaaclab.managers import EventTermCfg as EventTerm
from isaaclab.managers import ObservationGroupCfg as ObsGroup
from isaaclab.managers import ObservationTermCfg as ObsTerm
from isaaclab.managers import SceneEntityCfg
from isaaclab.managers import TerminationTermCfg as DoneTerm
from isaaclab.sensors import CameraCfg, FrameTransformerCfg, OffsetCfg
from isaaclab.utils.configclass import configclass

from openarm_autodata.shared.configs.camera_cfg import make_camera_cfgs
from openarm_autodata.shared.configs.robot_v2_cfg import (
    OPENARM_V2_GRASP_FRAME_OFFSET_POS,
    OPENARM_V2_GRASP_FRAME_OFFSET_ROT,
    OPENARM_V2_RIGHT_ARM_JOINT_NAMES,
    OPENARM_V2_RIGHT_EE_BODY_NAME,
    OPENARM_V2_RIGHT_EE_BODY_REL_PATH,
    OPENARM_V2_RIGHT_FINGER_JOINT_NAMES,
    OPENARM_V2_RIGHT_GRIPPER_OPEN_POSITION,
    OPENARM_V2_ROOT_BODY_REL_PATH,
)
from openarm_autodata.shared.envs.actions import (
    HoldLastTargetDifferentialInverseKinematicsActionCfg,
    RateLimitedBinaryJointPositionActionCfg,
)
from openarm_autodata.shared.envs.cameras import rgb_image

from ..envs import mdp
from .scene_cfg import OpenArmBimanualSceneCfg
from .scene_layout import load_scene_layout

OPENARM_POSITION_ACTION_SCALE = 0.02
"""TCP translation represented by a unit relative action [m]."""

OPENARM_ROTATION_ACTION_SCALE = 0.10
"""TCP axis-angle rotation represented by a unit relative action [rad]."""


_CAMERAS = make_camera_cfgs()


@configclass
class OpenArmBimanualTaskSceneCfg(OpenArmBimanualSceneCfg):
    """Bimanual scene with a TCP frame sensor and three calibrated RGB cameras."""

    left_hand_camera: CameraCfg = _CAMERAS["left_hand_camera"]
    right_hand_camera: CameraCfg = _CAMERAS["right_hand_camera"]
    third_person_camera: CameraCfg = _CAMERAS["third_person_camera"]

    ee_frame = FrameTransformerCfg(
        prim_path=f"{{ENV_REGEX_NS}}/Robot/{OPENARM_V2_ROOT_BODY_REL_PATH}",
        target_frames=[
            FrameTransformerCfg.FrameCfg(
                prim_path=f"{{ENV_REGEX_NS}}/Robot/{OPENARM_V2_RIGHT_EE_BODY_REL_PATH}",
                name="right_tcp",
                offset=OffsetCfg(
                    pos=OPENARM_V2_GRASP_FRAME_OFFSET_POS,
                    rot=OPENARM_V2_GRASP_FRAME_OFFSET_ROT,
                ),
            )
        ],
        debug_vis=False,
    )


@configclass
class ActionsCfg:
    """Right-arm relative TCP-pose and gripper actions for the full robot."""

    right_arm_action = HoldLastTargetDifferentialInverseKinematicsActionCfg(
        asset_name="robot",
        joint_names=list(OPENARM_V2_RIGHT_ARM_JOINT_NAMES),
        body_name=OPENARM_V2_RIGHT_EE_BODY_NAME,
        body_offset=base_mdp.DifferentialInverseKinematicsActionCfg.OffsetCfg(
            pos=OPENARM_V2_GRASP_FRAME_OFFSET_POS,
            rot=OPENARM_V2_GRASP_FRAME_OFFSET_ROT,
        ),
        controller=DifferentialIKControllerCfg(
            command_type="pose",
            use_relative_mode=True,
            ik_method="dls",
            ik_params={"lambda_val": 0.05},
        ),
        scale=(
            OPENARM_POSITION_ACTION_SCALE,
            OPENARM_POSITION_ACTION_SCALE,
            OPENARM_POSITION_ACTION_SCALE,
            OPENARM_ROTATION_ACTION_SCALE,
            OPENARM_ROTATION_ACTION_SCALE,
            OPENARM_ROTATION_ACTION_SCALE,
        ),
        hold_action_threshold=1.0e-6,
        max_joint_velocity=2.0,
    )
    right_gripper_action = RateLimitedBinaryJointPositionActionCfg(
        asset_name="robot",
        joint_names=list(OPENARM_V2_RIGHT_FINGER_JOINT_NAMES),
        open_command_expr={
            joint_name: OPENARM_V2_RIGHT_GRIPPER_OPEN_POSITION for joint_name in OPENARM_V2_RIGHT_FINGER_JOINT_NAMES
        },
        close_command_expr={joint_name: 0.0 for joint_name in OPENARM_V2_RIGHT_FINGER_JOINT_NAMES},
        max_velocity=1.0,
    )


@configclass
class ObservationsCfg:
    """Robot, object, action, and automatic annotation observations."""

    @configclass
    class PolicyCfg(ObsGroup):
        left_hand_rgb = ObsTerm(func=rgb_image, params={"name": "left_hand_camera"})
        right_hand_rgb = ObsTerm(func=rgb_image, params={"name": "right_hand_camera"})
        third_person_rgb = ObsTerm(func=rgb_image, params={"name": "third_person_camera"})
        joint_pos = ObsTerm(func=base_mdp.joint_pos_rel)
        joint_vel = ObsTerm(func=base_mdp.joint_vel_rel)
        right_tcp_pos = ObsTerm(func=mdp.tcp_position_in_robot_root_frame)
        right_tcp_quat = ObsTerm(func=mdp.tcp_orientation_in_robot_root_frame)
        right_tcp_pos_env = ObsTerm(func=mdp.tcp_position_in_env_frame)
        right_tcp_quat_env = ObsTerm(func=mdp.tcp_orientation_in_env_frame)
        cube_pose = ObsTerm(func=mdp.object_pose_in_robot_root_frame, params={"object_cfg": SceneEntityCfg("cube")})
        table_pose = ObsTerm(
            func=mdp.object_pose_in_robot_root_frame,
            params={"object_cfg": SceneEntityCfg("table")},
        )
        mousepad_pose: ObsTerm | None = None
        right_gripper_pos = ObsTerm(
            func=mdp.gripper_joint_position,
            params={
                "robot_cfg": SceneEntityCfg("robot", joint_names=[OPENARM_V2_RIGHT_FINGER_JOINT_NAMES[0]]),
            },
        )
        actions = ObsTerm(func=base_mdp.last_action)

        def __post_init__(self):
            self.enable_corruption = False
            self.concatenate_terms = False

    @configclass
    class SubtaskTermsCfg(ObsGroup):
        grasp = ObsTerm(
            func=mdp.cube_grasped,
            params={
                "robot_cfg": SceneEntityCfg("robot", joint_names=[OPENARM_V2_RIGHT_FINGER_JOINT_NAMES[0]]),
            },
        )

        def __post_init__(self):
            self.enable_corruption = False
            self.concatenate_terms = False

    policy: PolicyCfg = PolicyCfg()
    subtask_terms: SubtaskTermsCfg = SubtaskTermsCfg()


@configclass
class EventCfg:
    """Reset the scene and sample nearby pick-and-place layouts."""

    reset_all = EventTerm(func=base_mdp.reset_scene_to_default, mode="reset", params={"reset_joint_targets": True})
    reset_cube = EventTerm(
        func=base_mdp.reset_root_state_uniform,
        mode="reset",
        params={
            "pose_range": {},  # Filled from the selected scene layout.
            "velocity_range": {},
            "asset_cfg": SceneEntityCfg("cube"),
        },
    )


@configclass
class TerminationsCfg:
    """Episode termination conditions."""

    time_out = DoneTerm(func=base_mdp.time_out, time_out=True)
    cube_dropped = DoneTerm(func=mdp.cube_below_table)
    success = DoneTerm(
        func=mdp.cube_placed_on_pad,
        params={
            "robot_cfg": SceneEntityCfg("robot", joint_names=[OPENARM_V2_RIGHT_FINGER_JOINT_NAMES[0]]),
        },
    )


@configclass
class OpenArmBimanualPickPlaceEnvCfg(ManagerBasedRLEnvCfg):
    """Fixed-layout OpenArm bimanual pick-and-place environment."""

    scene_name: str = "gs_table"
    """Task-local layout selected by the registered environment variant."""
    table_height: float = 1.063
    cube_half_size: float = 0.019
    placement_footprint: tuple[tuple[float, float], ...] = ()
    placement_surface_z: float = 0.0
    placement_asset_name: str = "table"

    scene: OpenArmBimanualTaskSceneCfg = OpenArmBimanualTaskSceneCfg(
        num_envs=1,
        env_spacing=2.0,
        replicate_physics=False,
    )
    actions: ActionsCfg = ActionsCfg()
    observations: ObservationsCfg = ObservationsCfg()
    events: EventCfg = EventCfg()
    terminations: TerminationsCfg = TerminationsCfg()

    commands = None
    rewards = None
    curriculum = None

    def __post_init__(self):
        self.seed = 1
        self.decimation = 4
        self.episode_length_s = 30.0
        self.sim.dt = 1.0 / 120.0
        self.sim.render_interval = self.decimation
        layout = load_scene_layout(self.scene_name)
        if not layout["ground_plane"]:
            self.scene.ground = None
        if "mousepad" in layout:
            pad = layout["mousepad"]
            self.scene.mousepad = RigidObjectCfg(
                prim_path="{ENV_REGEX_NS}/Mousepad",
                # Preserve the rigid-body state authored in the pad USD.
                spawn=sim_utils.UsdFileCfg(usd_path=pad["usd"]),
                init_state=RigidObjectCfg.InitialStateCfg(
                    pos=pad["position_env"],
                    rot=pad["orientation_env"],
                ),
            )
        self.scene.table.spawn.usd_path = layout["table_usd"]
        self.scene.table.init_state.pos = layout["table_position"]
        self.scene.table.init_state.rot = layout["table_orientation"]
        self.scene.robot.init_state.pos = layout["robot_position"]
        self.scene.nightstand.spawn.scale = layout.get("nightstand_scale")
        self.scene.nightstand.init_state.pos = layout["nightstand_position"]
        self.scene.nightstand.init_state.rot = layout["nightstand_orientation"]
        self.scene.cube.init_state.pos = layout["cube_spawn_right"]
        self.events.reset_cube.params["pose_range"] = layout["cube_spawn_offsets"]
        self.table_height = layout["table_height"]
        self.cube_half_size = layout["cube_half_size"]
        self.placement_footprint = layout["pad_footprint"]
        self.placement_surface_z = layout["pad_surface_z"]
        if "mousepad" in layout:
            self.placement_asset_name = "mousepad"
            self.placement_footprint = layout["mousepad"]["footprint"]
            self.placement_surface_z = layout["mousepad"]["surface_z"]
            self.observations.policy.mousepad_pose = ObsTerm(
                func=mdp.object_pose_in_robot_root_frame,
                params={"object_cfg": SceneEntityCfg("mousepad")},
            )
        self.terminations.cube_dropped.params["minimum_height"] = self.table_height - 0.10
        self.terminations.success.params.update(
            table_cfg=SceneEntityCfg(self.placement_asset_name),
            pad_footprint=self.placement_footprint,
            pad_surface_z=self.placement_surface_z,
            cube_half_size=self.cube_half_size,
        )
