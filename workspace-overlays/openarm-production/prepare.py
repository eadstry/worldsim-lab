# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Verify the delivery manifest and assemble a local AutoData package without installing it."""

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path, PurePosixPath

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("archive", type=Path)
parser.add_argument("--destination", type=Path, default=Path(__file__).resolve().parent / "runtime")
args = parser.parse_args()
destination = args.destination.resolve()
assert not destination.exists(), f"Already prepared: {destination}"
with zipfile.ZipFile(args.archive) as archive:
    manifests = [name for name in archive.namelist() if name.count("/") == 1 and name.endswith("/MANIFEST.json")]
    assert len(manifests) == 1, "Expected a single delivery manifest"
    prefix = manifests[0].rsplit("/", 1)[0] + "/"
    manifest = json.loads(archive.read(manifests[0]))
    for item in manifest["files"]:
        path = PurePosixPath(item["path"])
        assert not path.is_absolute() and ".." not in path.parts, path
        payload = archive.read(prefix + str(path))
        assert len(payload) == item["bytes"], path
        assert hashlib.sha256(payload).hexdigest() == item["sha256"], path
    for name in archive.namelist():
        assert name.startswith(prefix), name
        path = PurePosixPath(name[len(prefix):])
        assert not path.is_absolute() and ".." not in path.parts, path
        if not path.parts or name.endswith("/"):
            continue
        if path.parts[0] not in {"openarm_autodata", "reference", "LICENSES"} and str(path) != "NOTICE.md":
            continue
        target = destination / str(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.read(name))

# reference/ contains the production files deliberately omitted from the Arena package.
reference = destination / "reference/openarm_autodata"
for source in reference.rglob("*"):
    if source.is_file():
        target = destination / "openarm_autodata" / source.relative_to(reference)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

# Extend only the delivered OpenArm config, keeping upstream's default planner unchanged.
shared_config = destination / "openarm_autodata/shared/planner_cfg.py"
source = shared_config.read_text()
source = source.replace("from pathlib import Path", "from curobo.util_file import load_yaml\nfrom pathlib import Path", 1)
source = source.replace("robot_config = super().get_robot_config()", 'robot_config = load_yaml(self.robot_config_file)["robot_cfg"]', 1)
source = source.replace("from pathlib import Path", "from pathlib import Path\nfrom isaaclab.utils.configclass import configclass")
source = source.replace("class OpenArmRightPlannerCfg(CuroboPlannerCfg):", "@configclass\nclass OpenArmRightPlannerCfg(CuroboPlannerCfg):")
anchor = "    def get_robot_config(self) -> dict:"
assert source.count(anchor) == 1
source = source.replace(anchor, '''    warmup: bool = False
    contact_offset_axis: tuple[float, float, float] = (0.0, 0.0, 1.0)
    gripper_closes_on_increasing_position: bool = True

''' + anchor)
shared_config.write_text(source)

# Create a process-local planner copy with the behavior needed by these OpenArm fields.
autodata = Path(__file__).resolve().parents[2] / "AutoData"
planner_source = autodata / "autodata_interfaces/motion_planners/curobo/curobo_planner.py"
source = planner_source.read_text()
replacements = {
    '    def get_ee_pose(self, joint_state: JointState) -> Pose:':
        '    def _compute_kinematics(self, joint_state: JointState):\n        active = joint_state.get_ordered_joint_state(self.motion_gen.kinematics.joint_names)\n        return self.motion_gen.compute_kinematics(active)\n\n    def get_ee_pose(self, joint_state: JointState) -> Pose:',
    'self.motion_gen.rollout_fn.compute_kinematics(cuda_joint_state)':
        'self._compute_kinematics(cuda_joint_state)',
    'self.motion_gen.compute_kinematics(js)': 'self._compute_kinematics(js)',
    '    def update_world_and_plan_motion(':
        '    @torch.inference_mode(False)\n    @torch.enable_grad()\n    def update_world_and_plan_motion(',
    '        self.motion_gen.update_locked_joints(locked_joints, self.robot_cfg)':
        '        all_locked_joints = dict(self.robot_cfg["kinematics"].get("lock_joints") or {})\n        all_locked_joints.update(locked_joints)\n        self.motion_gen.update_locked_joints(all_locked_joints, self.robot_cfg)',
    'robot_cfg: dict[str, Any] = load_yaml(robot_cfg_file)["robot_cfg"]':
        'robot_cfg: dict[str, Any] = self.config.get_robot_config()',
    '        self.motion_gen.warmup(enable_graph=True, warmup_js_trajopt=False)':
        '        if self.config.warmup:\n            self.motion_gen.warmup(enable_graph=True, warmup_js_trajopt=False)',
    'position=[0.0, 0.0, -retreat_distance]':
        'position=[retreat_distance * axis for axis in self.config.contact_offset_axis]',
    'position=[0.0, 0.0, -approach_distance]':
        'position=[approach_distance * axis for axis in self.config.contact_offset_axis]',
    'gripper_pos = self.datastream.get_robot_joint_positions(env_ids=[env_id])[0, -2:]':
        'gripper_indices = [self.datastream.get_robot_joint_names().index(name) for name in self.config.gripper_joint_names]\n        gripper_pos = self.datastream.get_robot_joint_positions(env_ids=[env_id])[0, gripper_indices]',
    'object_grasped = gripper_pos[0].item() < gripper_open_val':
        'object_grasped = (gripper_pos[0].item() > gripper_open_val if self.config.gripper_closes_on_increasing_position else gripper_pos[0].item() < gripper_open_val)',
}
for old, new in replacements.items():
    assert source.count(old) == 1, f"Planner changed; review replacement: {old}"
    source = source.replace(old, new, 1)
assert source.count('self.motion_gen.compute_kinematics(next_joint_state)') == 2
source = source.replace('self.motion_gen.compute_kinematics(next_joint_state)', 'self._compute_kinematics(next_joint_state)')
source = source.replace('        # Get all link states using the robot model',
    '        joint_state = joint_state.get_ordered_joint_state(self.motion_gen.kinematics.joint_names)\n\n        # Get all link states using the robot model', 1)
patched = destination / "patches/curobo_planner.py"
patched.parent.mkdir(parents=True, exist_ok=True)
compile(source, str(patched), "exec")
patched.write_text(source)

# The upstream adapter silently ignores the delivered action scales. Supply an overlay copy.
adapter_path = autodata / "autodata_interfaces/embodiments/single_arm_embodiment_adapter.py"
source = adapter_path.read_text()
replacements = {
    '    clip_pose_action_to_unit: bool = True':
        '    clip_pose_action_to_unit: bool = True\n    position_action_scale: float = 1.0\n    rotation_action_scale: float = 1.0\n    pose_action_limit: float = 1.0',
    'delta_pos = action[:, :3]': 'delta_pos = action[:, :3] * self.position_action_scale',
    'delta_aa = action[:, 3:6]': 'delta_aa = action[:, 3:6] * self.rotation_action_scale',
    'delta_pos = target_pos - curr_pos': 'delta_pos = (target_pos - curr_pos) / self.position_action_scale',
    'delta_aa = pose_math.axis_angle_from_quat(pose_math.quat_from_matrix(delta_rot))':
        'delta_aa = pose_math.axis_angle_from_quat(pose_math.quat_from_matrix(delta_rot)) / self.rotation_action_scale',
    'pose_action = torch.clamp(pose_action, -1.0, 1.0)':
        'pose_action = torch.clamp(pose_action, -self.pose_action_limit, self.pose_action_limit)',
    '            clip_pose_action_to_unit=bool(layout.get("clip_pose_action_to_unit", True)),':
        '            clip_pose_action_to_unit=bool(layout.get("clip_pose_action_to_unit", True)),\n            position_action_scale=float(layout.get("position_action_scale", 1.0)),\n            rotation_action_scale=float(layout.get("rotation_action_scale", 1.0)),\n            pose_action_limit=float(layout.get("pose_action_limit", 1.0)),',
}
for old, new in replacements.items():
    assert source.count(old) == 1, f"Adapter changed; review replacement: {old}"
    source = source.replace(old, new, 1)
patched = destination / "patches/single_arm_embodiment_adapter.py"
compile(source, str(patched), "exec")
patched.write_text(source)
report = {
    "archive_sha256": hashlib.sha256(args.archive.read_bytes()).hexdigest(),
    "manifest_files_verified": len(manifest["files"]),
    "runtime_validation": "not performed",
}
(destination / "preparation.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
