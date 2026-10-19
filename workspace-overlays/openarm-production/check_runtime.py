# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Check real OpenArm environment startup/steps; does not claim dataset generation."""

import sys
import json
import traceback
from pathlib import Path

root = Path(__file__).resolve().parent
sys.path[:0] = [str(root), str(root / "runtime"), str(root.parents[1] / "AutoData")]
from isaaclab.app import AppLauncher

launcher = AppLauncher(headless=True, enable_cameras=True, kit_args="--enable omni.usd.schema.omni_lens_distortion")
app = launcher.app
env = None
try:
    import torch
    import gymnasium as gym
    from compat import install

    install()
    from isaaclab_tasks.utils.parse_cfg import parse_env_cfg
    from autodata_interfaces.motion_planners.curobo.curobo_planner_cfg import CuroboPlannerCfg
    from autodata_interfaces.embodiments import embodiment_adapter_from_yaml

    task_id = "Isaac-PickPlace-Cube-OpenArm-Bimanual-Right-IK-Rel-v0"
    cfg = parse_env_cfg(task_id, device="cuda:0", num_envs=1)
    env = gym.make(task_id, cfg=cfg).unwrapped
    env.reset()
    for _ in range(3):
        env.step(torch.zeros(env.action_space.shape, device=env.device))
    planner = CuroboPlannerCfg.from_profile("openarm_pick_place")
    model = planner.get_robot_config()
    assert Path(model["kinematics"]["urdf_path"]).is_file()
    adapter = embodiment_adapter_from_yaml(root / "runtime/openarm_autodata/tasks/pick_place/autodata_configs/embodiments/openarm_bimanual_right_ik_rel.yaml", env=env)
    assert adapter.position_action_scale == 0.02 and adapter.rotation_action_scale == 0.10
    assert adapter.pose_action_limit == 0.2
    current = adapter.get_eef_poses(env_ids=[0])["right"][0]
    target = current.clone()
    target[0, 3] += 0.001
    action = adapter.target_eef_pose_to_action({"right": target}, {"right": torch.tensor([-1.0], device=env.device)})
    assert torch.isclose(action[0], torch.tensor(0.05, device=env.device), atol=1e-5)
    print("OPENARM_RUNTIME_CHECK_PASSED: right-arm env reset and 3 physics/control steps; planner config loaded", flush=True)
    (root / "runtime-check-result.json").write_text(json.dumps({"status": "passed", "steps": 3}))
except BaseException:
    details = traceback.format_exc()
    (root / "runtime-check-result.json").write_text(json.dumps({"status": "failed", "traceback": details}, indent=2))
    print(details, file=sys.__stderr__, flush=True)
    raise
finally:
    if env is not None:
        env.close()
    app.close()
