"""Keep OpenArm gripper rate limiting compatible with Warp joint indices."""

from isaaclab.envs.mdp.actions.binary_joint_actions import BinaryJointPositionAction
from openarm_autodata.shared.envs.actions import RateLimitedBinaryJointPositionAction


class CompatibleGripperAction(RateLimitedBinaryJointPositionAction):
    """Use Torch indices for reads and original backend indices for target writes."""

    def __init__(self, cfg, env):
        BinaryJointPositionAction.__init__(self, cfg, env)
        self._max_position_step = self.cfg.max_velocity * self._env.physics_dt
        self._read_joint_ids = self._joint_ids
        import warp as wp

        if isinstance(self._read_joint_ids, wp.array):
            self._read_joint_ids = wp.to_torch(self._read_joint_ids).long()
        self._applied_targets = self._asset.data.default_joint_pos.torch[:, self._read_joint_ids].clone()

    def reset(self, env_ids=None):
        BinaryJointPositionAction.reset(self, env_ids)
        if env_ids is None:
            env_ids = slice(None)
        positions = self._asset.data.joint_pos.torch[:, self._read_joint_ids]
        self._applied_targets[env_ids] = positions[env_ids]
