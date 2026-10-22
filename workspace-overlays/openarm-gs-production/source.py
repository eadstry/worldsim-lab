# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Collect a test source for the supplied GS task using actual physics and AutoData observations."""
import argparse
import json
import hashlib
import os
from pathlib import Path
import sys
import traceback

p = argparse.ArgumentParser()
p.add_argument('--workspace', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--reference', type=Path, required=True)
a = p.parse_args()
assert hashlib.sha256(a.reference.read_bytes()).hexdigest() == '7321968fb3f0037b2b7d94bcaa0f0c0ff609c99c89671cd443fcd210c4fec2da', 'Reference differs from the reviewed test fixture'
a.output.mkdir(parents=True, exist_ok=False)
root = Path(__file__).resolve().parent
sys.path[:0] = [str(root / 'runtime'), str(a.workspace / 'AutoData'), str(a.workspace / 'workspace-overlays/openarm-production')]
os.environ['OPENARM_TELEMETRY_FILE'] = str(a.output / 'telemetry.jsonl')
from isaaclab.app import AppLauncher
app = AppLauncher(headless=True, enable_cameras=True, kit_args='--enable omni.usd.schema.omni_lens_distortion').app
exit_code = 1
try:
    import h5py
    import numpy as np
    import torch
    import gymnasium as gym
    from compat import install
    install()
    from autodata_interfaces.datastream import Datastream
    from autodata_core.pool import DataGenInfoPool
    from autodata_interfaces.embodiments import embodiment_adapter_from_yaml
    from autodata_interfaces.tasks.task_descriptor import TaskDescriptor
    from isaaclab_tasks.utils import parse_env_cfg
    configs = root / 'runtime/openarm_autodata/tasks/pick_place/autodata_configs'
    task = TaskDescriptor.from_yaml(configs / 'tasks/openarm_bimanual_left_pick_place.yaml')
    env_name = 'Isaac-PickPlace-Cube-OpenArm-GS-Bimanual-Left-IK-Rel-v0'
    cfg = parse_env_cfg(env_name, device='cuda:0', num_envs=1)
    success_term = cfg.terminations.success
    cfg.terminations = None
    cfg.recorders = None
    cfg.seed = 1
    env = gym.make(env_name, cfg=cfg).unwrapped
    env.reset()
    adapter = embodiment_adapter_from_yaml(configs / 'embodiments/openarm_bimanual_left_ik_rel.yaml')
    pool = DataGenInfoPool(task, adapter, env.device, uses_start_signals=True)
    stream = Datastream(env, task, adapter, source_pool=pool, uses_start_signals=True)
    initial = env.scene.get_state(is_relative=True)
    def host(x):
        return x.detach().cpu().numpy() if isinstance(x, torch.Tensor) else x.torch.detach().cpu().numpy()
    def save_tree(group, tree):
        for k,v in tree.items():
            if isinstance(v,dict): save_tree(group.create_group(k),v)
            else: group.create_dataset(k,data=host(v))
    actions, records, measurements = [], {}, []
    cube = env.scene['cube'].data.root_pos_w.torch[0].clone()
    cube_z = float(cube[2])
    pad = env.scene['mousepad'].data.root_pos_w.torch[0].clone()
    print('INITIAL', cube.tolist(), pad.tolist(), env.obs_buf['policy']['left_tcp_pos_env'][0].tolist(), flush=True)
    # Use measured reference poses as a test demonstration controller, retargeted to
    # the current cube and pad. Re-record all states; never relabel old scene data.
    with h5py.File(a.reference,'r') as f:
        ref=f['data/demo_0']
        target_poses=ref['obs/datagen_info/target_eef_pose/left'][:]
        reference_actions=ref['actions'][:]
        old_cube=ref['obs/datagen_info/object_pose/cube'][0,:3,3]
        old_destination=ref['obs/datagen_info/object_pose/cube'][-1,:3,3]
    pick_shift=cube-cube.new_tensor(old_cube)
    destination=pad.clone();destination[2]+=0.00083+0.019
    place_shift=destination-cube.new_tensor(old_destination)
    boundaries={'descend':424,'lower':944}
    with torch.inference_mode():
        for index in range(len(target_poses)+180):
            ref_index=min(index,len(target_poses)-1)
            blend=max(0.,min(1.,(index-700)/244))
            shift=(1-blend)*pick_shift+blend*place_shift
            target=cube.new_tensor(target_poses[ref_index])
            target[:3,3]+=shift
            grip=cube.new_tensor([reference_actions[ref_index,-1]])
            action=adapter.target_eef_pose_to_action({'left':target},{'left':grip}).unsqueeze(0)
            for field,values in [('object_pose',stream.get_object_poses()),('eef_pose',adapter.get_eef_poses()),('target_eef_pose',stream.action_to_target_eef_pose(action))]:
                for name,value in values.items():records.setdefault(field+'/'+name,[]).append(host(value)[0])
            actions.append(host(action)[0])
            obs,*_=env.step(action)
            cp=host(env.scene['cube'].data.root_pos_w)[0]
            measurements.append({'phase':'reference-retarget','cube':cp.tolist(),'tcp':host(obs['policy']['left_tcp_pos_env'])[0].tolist(),
                                 'grasp':bool(obs['subtask_terms']['grasp'][0]),'success':bool(success_term.func(env,**success_term.params)[0])})
            if index%100==0:print(index,measurements[-1],flush=True)
    succeeded=all(x['success'] for x in measurements[-60:])
    stable=[i for i,m in enumerate(measurements) if m['grasp'] and m['cube'][2]>=cube_z+.08]
    result={'success':succeeded,'stable_lift':bool(stable),'frames':len(actions),'phases':boundaries,'measurements':measurements}
    (a.output/'source-check.json').write_text(json.dumps(result,indent=2))
    assert succeeded and stable, 'Source failed original GS lift/place criteria; do not use as SkillGen source'
    assert boundaries['descend'] < stable[0] < boundaries['lower'] < len(actions)
    count=len(actions)
    with h5py.File(a.output/'source.hdf5','x') as f:
        data=f.create_group('data');data.attrs['env_args']=json.dumps({'env_name':env_name,'type':2});data.attrs['total']=count
        demo=data.create_group('demo_0');demo.attrs.update(num_samples=count,success=True)
        demo.attrs['annotation_provenance']=json.dumps({'source':'Measured GS task source controlled by retargeted reference EEF poses; experimental boundaries, not human annotated', 'reference':str(a.reference),'phases':boundaries})
        save_tree(demo.create_group('initial_state'),initial)
        demo.create_dataset('actions',data=np.stack(actions))
        for key,values in records.items():demo.create_dataset('obs/datagen_info/'+key,data=np.stack(values),compression='gzip')
        for kind,signal,boundary in [('subtask_start_signals','grasp',boundaries['descend']),('subtask_term_signals','grasp',stable[0]),('subtask_start_signals','place',boundaries['lower'])]:
            demo.create_dataset('obs/datagen_info/'+kind+'/'+signal,data=np.arange(count)>=boundary)
    env.close()
    exit_code=0
except BaseException:
    traceback.print_exc()
finally:
    app.close(exit_code=exit_code)
