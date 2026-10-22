# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Replay the generated GS episode from a new robot-mounted virtual head camera."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback

p=argparse.ArgumentParser()
p.add_argument('--workspace',type=Path,required=True)
p.add_argument('--input',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
root=Path(__file__).resolve().parent
sys.path[:0]=[str(root/'runtime'),str(a.workspace/'AutoData'),str(a.workspace/'workspace-overlays/openarm-production')]
os.environ['OPENARM_TELEMETRY_FILE']=str(a.output/'telemetry.jsonl')
from isaaclab.app import AppLauncher
app=AppLauncher(headless=True,enable_cameras=True,kit_args='--enable omni.usd.schema.omni_lens_distortion').app
exit_code=1;video=None;env=None
try:
    import h5py
    import numpy as np
    import torch
    import gymnasium as gym
    import imageio_ffmpeg
    from PIL import Image
    from compat import install
    install()
    from isaaclab.sensors import CameraCfg
    from isaaclab.sim import PinholeCameraCfg
    from isaaclab_tasks.utils import parse_env_cfg
    task_id='Isaac-PickPlace-Cube-OpenArm-GS-Bimanual-Left-IK-Rel-v0'
    cfg=parse_env_cfg(task_id,device='cuda:0',num_envs=1)
    success_term=cfg.terminations.success;cfg.terminations=None;cfg.recorders=None
    head=json.loads((root/'configs/head_preview.json').read_text())
    camera_prim='{ENV_REGEX_NS}/Robot/'+head['mount_relative_to_robot']
    cfg.scene.head_preview_camera=CameraCfg(prim_path=camera_prim,update_period=0.,height=head['height'],width=head['width'],
        data_types=['rgb'],spawn=PinholeCameraCfg(focal_length=head['focal_length_mm'],
            horizontal_aperture=head['horizontal_aperture_mm'],vertical_aperture=head['vertical_aperture_mm'],clipping_range=(.01,100.)))
    env=gym.make(task_id,cfg=cfg).unwrapped
    def tensor(x):return x if isinstance(x,torch.Tensor) else x.torch
    def load_tree(group):return {k:load_tree(v) if isinstance(v,h5py.Group) else torch.as_tensor(v[:],device=env.device) for k,v in group.items()}
    with h5py.File(a.input,'r') as f:
        names=list(f['data']);assert len(names)==1,names
        episode=f['data/'+names[0]]
        actions=episode['actions'][:]
        expected=episode['states/rigid_object/cube/root_pose'][:,:3]
        initial=load_tree(episode['initial_state'])
        recorded_success=bool(episode.attrs['success'])
        assert actions.shape[1]==7 and np.isfinite(actions).all() and recorded_success
        streams={k:list(episode['obs/'+k].shape) for k in ('left_hand_rgb','right_hand_rgb','third_person_rgb')}
    env.reset()
    env.scene.reset_to(initial,env_ids=torch.tensor([0],device=env.device),is_relative=True)
    env.obs_buf=env.observation_manager.compute()
    camera=env.scene['head_preview_camera']
    camera.set_world_poses_from_view(env.scene.env_origins+torch.tensor(head['eye_env_m'],device=env.device),
        env.scene.env_origins+torch.tensor(head['look_at_env_m'],device=env.device))
    for _ in range(8):env.sim.render()
    video=imageio_ffmpeg.write_frames(str(a.output/'task.mp4'),(1280,960),fps=15,codec='libx264',pix_fmt_in='rgb24',pix_fmt_out='yuv420p',output_params=['-crf','18'])
    video.send(None)
    states=[];frames=0
    with torch.inference_mode():
        for i,action in enumerate(actions):
            obs,*_=env.step(torch.as_tensor(action,device=env.device).unsqueeze(0))
            cube=tensor(env.scene['cube'].data.root_pos_w)[0].cpu().numpy()
            pad=tensor(env.scene['mousepad'].data.root_pos_w)[0].cpu().numpy()
            states.append({'step':i,'cube':cube.tolist(),'mousepad':pad.tolist(),
                           'success':bool(success_term.func(env,**success_term.params)[0]),
                           'grasp':bool(obs['subtask_terms']['grasp'][0])})
            if i%2==0:
                camera.update(env.step_dt,force_recompute=True)
                rgb=tensor(camera.data.output['rgb'])[0,...,:3].cpu().numpy()
                video.send(rgb);frames+=1
                if frames in (1,100,300) or i>=len(actions)-2:Image.fromarray(rgb).save(a.output/f'frame-{frames:04d}.png')
            if i%200==0:print('REPLAY',i,states[-1],flush=True)
    video.close();video=None
    errors=np.linalg.norm(np.array([s['cube'] for s in states])-expected,axis=1)
    final_success=all(s['success'] for s in states[-30:])
    report={'task':task_id,'input_sha256':hashlib.sha256(a.input.read_bytes()).hexdigest(),'recorded_success':recorded_success,
            'replay_final_success':final_success,'frames':frames,'fps':15,'duration_s':frames/15,'steps':len(actions),'step_dt':env.step_dt,
            'resolution':[1280,960],'rgb_stream_shapes':streams,'camera':head,'camera_prim':camera_prim,
            'max_cube_position_difference_m':float(errors.max()),'final_cube_position_difference_m':float(errors[-1]),
            'video_sha256':hashlib.sha256((a.output/'task.mp4').read_bytes()).hexdigest(),'states':states}
    (a.output/'replay-check.json').write_text(json.dumps(report,indent=2))
    assert final_success,'Generated episode did not retain original GS success under independent replay'
    print(json.dumps({k:v for k,v in report.items() if k!='states'},indent=2),flush=True)
    exit_code=0
except BaseException:
    traceback.print_exc()
finally:
    if video is not None:video.close()
    if env is not None:env.close()
    app.close(exit_code=exit_code)
