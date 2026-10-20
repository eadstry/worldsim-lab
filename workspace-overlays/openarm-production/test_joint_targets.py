"""Check native/control ordering, measurement-vs-command and export ownership."""
import copy
import unittest

import torch

from joint_targets import attach
from test_dataset_metadata import environment
from dataset_metadata import attach as attach_metadata


class JointTargetTests(unittest.TestCase):
    def setup_env(self):
        env = environment()
        robot = env.scene['robot']
        robot.data.joint_pos = torch.arange(36, dtype=torch.float32).reshape(2, 18)
        pose = env.action_manager.get_term('left_arm_action')
        finger = env.action_manager.get_term('left_gripper_action')
        pose.cfg.max_joint_velocity = 2.0
        finger.cfg.max_velocity = 1.0
        pose._joint_pos_command = torch.arange(14, dtype=torch.float32).reshape(2, 7) + 100
        pose._joint_pos_target = pose._joint_pos_command - 10
        finger.processed_actions = torch.tensor([[.2, .4], [.6, .8]])
        finger._applied_targets = finger.processed_actions - .1
        rows = {}
        env.recorder_manager.record_pre_step = lambda: rows.update(original_pre=True)
        env.recorder_manager.record_post_step = lambda: rows.update(original_post=True)
        env.recorder_manager.add_to_episodes = lambda k,v: rows.setdefault(k, []).append(v.clone())
        attach_metadata(env)
        return env, rows, pose, finger

    def test_state_and_command_same_order_but_distinct_values_and_owned_snapshots(self):
        env, rows, pose, finger = self.setup_env()
        attach(env)
        attach(env)  # must not record twice
        rec = env.recorder_manager
        rec.record_pre_step()
        rec.record_post_step()
        schema = rec.get_ep_meta()['semantic_metadata']
        keys = schema['joint_control']['names']
        self.assertEqual(keys, [f'openarm_left_joint{i}' for i in range(1,8)] + ['openarm_left_finger_joint1', 'openarm_left_finger_joint2'])
        self.assertEqual(schema['fields']['joint_actions']['names'], schema['fields']['obs/joint_pos_absolute']['names'])
        ids = [env.scene['robot'].joint_names.index(k) for k in keys]
        torch.testing.assert_close(rows['obs/joint_pos_absolute'][0], env.scene['robot'].data.joint_pos[:, ids])
        torch.testing.assert_close(rows['joint_actions'][0][:,:7], pose._joint_pos_command)
        # Mock native fingers are 2 then 1, output must be canonical 1 then 2.
        torch.testing.assert_close(rows['joint_actions'][0][:,7:], finger.processed_actions[:, [1,0]])
        torch.testing.assert_close(rows['joint_applied_targets'][0][:,:7], pose._joint_pos_target)
        self.assertFalse(torch.equal(rows['joint_actions'][0], rows['obs/joint_pos_absolute'][0]))
        saved = rows['joint_actions'][0].clone()
        pose._joint_pos_command.zero_()
        torch.testing.assert_close(rows['joint_actions'][0], saved)
        self.assertEqual(len(rows['joint_actions']), 1)
        schema['joint_control']['names'][0] = 'bad'
        self.assertNotEqual(rec.get_ep_meta()['semantic_metadata']['joint_control']['names'][0], 'bad')
        self.assertTrue(rows['original_pre'] and rows['original_post'])

    def test_unknown_controller_rejected_before_recorder_is_changed(self):
        env, rows, pose, _ = self.setup_env()
        original = env.recorder_manager.record_pre_step
        del pose._joint_pos_command
        with self.assertRaisesRegex(ValueError, 'verified'):
            attach(env)
        self.assertIs(env.recorder_manager.record_pre_step, original)


if __name__ == '__main__':
    unittest.main()
