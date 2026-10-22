# SPDX-FileCopyrightText: 2026
# SPDX-License-Identifier: MIT
"""Recheck saved states: lift duration, released placement, stability and contact."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--g1d',action='store_true');a=p.parse_args()
r=json.loads((a.run/'trajectory.json').read_text());v=json.loads((a.run/'verification.json').read_text())
x=np.asarray([f['cubes'] for f in r]);assert np.isfinite(x).all()
time=np.asarray([f.get('time',i/30) for i,f in enumerate(r)]);assert np.allclose(np.diff(time),1/30,atol=1e-7)
n=len(v['checks']) if a.g1d else 3;goals=np.asarray(v.get('goals',[[.48,-.21,.022],[.58,-.21,.022],[.68,-.21,.022]]))
checks=[]
for i,c in enumerate(['red','green','blue'][:n]):
    lift_frames=[k for k,f in enumerate(r) if f['phase'] in [c+'_lift',c+'_transfer']]
    held=int(np.count_nonzero(x[lift_frames,i,2]-x[0,i,2]>.12))
    final=x[-30:,i];max_error=float(np.linalg.norm(final[:,:2]-goals[i,:2],axis=1).max());max_speed=float(np.linalg.norm(np.diff(final,axis=0),axis=1).max()*30)
    stable=max_error<.035 and float(np.abs(final[:,2]-.022).max())<.012 and max_speed<.02
    if a.g1d:
        open_fingers=all(f['joints'].get('demo_close_left',100)<.004 and f['joints'].get('demo_close_right',100)<.004 for f in r[-30:])
        tool=v['body_names'].index('demo_gripper');separation=min(np.linalg.norm(np.asarray(f['body_pos'][tool])-np.asarray(f['cubes'][i])) for f in r[-30:])
        contact_frames=sum(any(('cube_'+c in pair and any(str(z).startswith('demo_pad') for z in pair)) for pair in f['contacts']) for f in r)
        assert contact_frames>5,'No recorded jaw/cube contact'
    else:
        open_fingers=all(max(abs(t) for t in f['fingers'])<.004 for f in r[-30:]);separation=min(np.linalg.norm(np.asarray(f['hand'])-np.asarray(f['cubes'][i])) for f in r[-30:]);contact_frames=None
    assert held>=15 and stable and open_fingers and separation>.10,(c,held,stable,open_fingers,separation)
    checks.append(dict(color=c,held_above_12cm_frames=held,final_max_xy_error_m=max_error,final_max_speed_m_s=max_speed,open_fingers=open_fingers,min_final_gripper_separation_m=float(separation),jaw_cube_contact_frames=contact_frames))
if n==3:assert np.all(np.diff(x[-1,:,0])>0),'Final color order is not R-G-B along world +X'
result=dict(passed=True,frames=len(r),simulation_seconds=float(time[-1]-time[0]+1/30),checks=checks,trajectory_sha256=hashlib.sha256((a.run/'trajectory.json').read_bytes()).hexdigest(),scope='Independent state-level recomputation; no policy/generalization or whole-house collision validation')
(a.run/'independent-verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
