# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Robot-mounted RGB cameras using calibrated OpenCV pinhole K/D and ROS offsets."""

from __future__ import annotations

import json
import numpy as np
import torch
from collections.abc import Callable
from pathlib import Path

from isaaclab.sensors import CameraCfg
from isaaclab.sim import PinholeCameraCfg
from isaaclab.sim.spawners.sensors import spawn_camera
from isaaclab.sim.utils import clone
from isaaclab.utils.configclass import configclass
from isaaclab.utils.math import quat_from_matrix
from pxr import Gf, Usd

from openarm_autodata.shared.configs.robot_v2_cfg import (
    OPENARM_V2_RIGHT_EE_BODY_REL_PATH,
    OPENARM_V2_ROOT_BODY_REL_PATH,
)

CALIBRATION_PATH = Path(__file__).resolve().parents[1] / "calibration/cameras.json"
_CAMERA_CALIBRATIONS = json.loads(CALIBRATION_PATH.read_text())["cameras"]


@clone
def spawn_calibrated_camera(
    prim_path: str,
    cfg: CalibratedPinholeCameraCfg,
    translation: tuple[float, float, float] | None = None,
    orientation: tuple[float, float, float, float] | None = None,
    **kwargs,
) -> Usd.Prim:
    """Spawn an Isaac Lab camera with the renderer's native OpenCV lens schema.

    Args:
        prim_path: Camera prim path or environment path pattern.
        cfg: Camera and calibrated lens settings.
        translation: Position relative to the parent [m].
        orientation: Rotation relative to the parent as an xyzw quaternion.
        **kwargs: Additional arguments for the official camera spawner.
    """
    # Only pass standard fields to the official spawner; lens fields use their own schema.
    base = PinholeCameraCfg()
    for name in vars(base):
        if name != "func":
            setattr(base, name, getattr(cfg, name))
    prim = spawn_camera(prim_path, base, translation=translation, orientation=orientation, **kwargs)
    assert prim.ApplyAPI("OmniLensDistortionOpenCvPinholeAPI"), "OpenCV lens schema is unavailable"
    prim.GetAttribute("omni:lensdistortion:model").Set("opencvPinhole")
    prefix = "omni:lensdistortion:opencvPinhole:"
    intrinsic = np.array(cfg.intrinsic_matrix).reshape(3, 3)
    parameters = dict(cx=intrinsic[0, 2], cy=intrinsic[1, 2], fx=intrinsic[0, 0], fy=intrinsic[1, 1])
    parameters.update(dict(zip(("k1", "k2", "p1", "p2", "k3"), cfg.distortion_coefficients)))
    parameters.update(k4=0.0, k5=0.0, k6=0.0)
    for name, value in parameters.items():
        assert prim.GetAttribute(prefix + name).Set(float(value)), name
    assert prim.GetAttribute(prefix + "imageSize").Set(Gf.Vec2i(*cfg.image_size))
    return prim


@configclass
class CalibratedPinholeCameraCfg(PinholeCameraCfg):
    """Standard camera spawner extended with native OpenCV pinhole calibration."""

    func: Callable = spawn_calibrated_camera
    intrinsic_matrix: tuple[float, ...] = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
    distortion_coefficients: tuple[float, ...] = (0.0,) * 5
    """OpenCV plumb_bob coefficients in k1, k2, p1, p2, k3 order."""
    image_size: tuple[int, int] = (640, 480)


@configclass
class CameraCaptureCfg:
    """Shared output settings; scene control/render timing must match the capture rate."""

    width: int = 640
    height: int = 480
    fps: float = 30.0
    clipping_range: tuple[float, float] = (0.01, 100.0)
    """Near and far clipping distances [m]."""


def make_camera_cfgs(
    capture: CameraCaptureCfg | None = None,
) -> dict[str, CameraCfg]:
    """Create two wrist cameras and a camera fixed to the robot base.

    Args:
        capture: Shared RGB output settings. Defaults to 640x480 at 30 Hz.

    Returns:
        Scene sensor configs named left_hand_camera, right_hand_camera and
        third_person_camera. These are not added to any scene automatically.
    """
    capture = CameraCaptureCfg() if capture is None else capture
    assert capture.width > 0 and capture.height > 0 and capture.fps > 0
    cameras = {}
    for name, calibration in _CAMERA_CALIBRATIONS.items():
        intrinsic = np.array(calibration["intrinsic_matrix"], dtype=float).reshape(3, 3)
        scale = max(capture.width / calibration["width"], capture.height / calibration["height"])
        intrinsic[:2] *= scale
        intrinsic[0, 2] -= (calibration["width"] * scale - capture.width) / 2
        intrinsic[1, 2] -= (calibration["height"] * scale - capture.height) / 2

        assert calibration["distortion_model"] == "plumb_bob"
        distortion = tuple(calibration["distortion_coefficients"])
        assert len(distortion) == 5
        pose = np.array(calibration["T_parent_ros_optical"], dtype=float)
        if name == "third_person":
            assert calibration["parent_frame"] == "openarm_right_base_link"
            # This camera is physically fixed to the robot, not to the room.
            link_path = f"{OPENARM_V2_ROOT_BODY_REL_PATH}/openarm_right_base_link"
        else:
            link_path = OPENARM_V2_RIGHT_EE_BODY_REL_PATH
            if name == "left_hand":
                link_path = link_path.replace("right", "left")
        assert link_path.rsplit("/", 1)[-1] == calibration["parent_frame"]
        prim_path = f"{{ENV_REGEX_NS}}/Robot/{link_path}/{name}_camera"

        rotation = tuple(quat_from_matrix(torch.as_tensor(pose[:3, :3])).tolist())
        cameras[f"{name}_camera"] = CameraCfg(
            prim_path=prim_path,
            update_period=1.0 / capture.fps,
            width=capture.width,
            height=capture.height,
            data_types=["rgb"],
            spawn=CalibratedPinholeCameraCfg(
                intrinsic_matrix=tuple(intrinsic.reshape(-1).tolist()),
                distortion_coefficients=distortion,
                image_size=(capture.width, capture.height),
                # USD perspective attributes provide a fallback; RTX uses the exact lens K/D above.
                focal_length=24.0,
                horizontal_aperture=24.0 * capture.width / intrinsic[0, 0],
                vertical_aperture=24.0 * capture.height / intrinsic[1, 1],
                clipping_range=capture.clipping_range,
            ),
            offset=CameraCfg.OffsetCfg(
                pos=tuple(pose[:3, 3].tolist()),
                rot=rotation,
                convention="ros",
            ),
            update_latest_camera_pose=True,
        )
    return cameras
