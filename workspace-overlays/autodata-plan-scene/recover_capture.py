# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Reconcile rendered frame files against HDF5 after Isaac Sim terminates Python.

Isaac Sim shutdown can exit before the outer Python finally block. The planner
snapshots remain partial, but every capture has a deterministic step number.
Validate their alignment against recorded live states before recovering the tail.
"""
import argparse
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np

parser=argparse.ArgumentParser()
parser.add_argument('run_root',type=Path)
args=parser.parse_args()
for name in ('baseline','offset-a','offset-b'):
    folder=args.run_root/name
    probe=json.loads((folder/'probe.json').read_text())
    original_frames=probe['frames']
    assert original_frames, name
    with h5py.File(folder/'episodes.hdf5','r') as f:
        assert len(f['data'])==1, 'Expected exactly one attempted episode'
        g=next(iter(f['data'].values()))
        steps=len(g['actions'])
        eef=g['obs/left_tcp_pos_env'][:]
        cube=g['states/rigid_object/cube/root_pose'][:,:3]
        # Observations are at the start of a step; the recorder's root state is
        # stored at the end of the preceding action. Both align exactly with the
        # live post-step capture with these independently checked indices.
        for frame in original_frames:
            s=frame['step']
            assert np.allclose(eef[s],frame['eef_position_m'],atol=1e-6,rtol=0),(name,s,'eef')
            assert np.allclose(cube[s-1],frame['cube_position_m'],atol=1e-6,rtol=0),(name,s,'cube')
        assert original_frames[0]['step']==1
        dt=original_frames[0]['time_s']
        files=sorted(folder.glob('frame-*.jpg'))
        expected=1+steps//20
        assert len(files)==expected,(name,len(files),expected)
        new_frames=[]
        for i,file in enumerate(files):
            assert file.name==f'frame-{i:04d}.jpg'
            s=1 if i==0 else i*20
            assert s<len(eef),'Last captured frame needs the following pre-step observation'
            active=[p for p in probe['plans'] if p['start_step']<s]
            current=active[-1] if active else None
            kind='curobo_transit'
            if current and s>=current['start_step']+len(current['eef_positions_m']):kind='skill_replay'
            if s>=steps-60:kind='final_hold'
            new_frames.append({'file':file.name,'step':s,'time_s':s*dt,'eef_position_m':eef[s].tolist(),
                               'cube_position_m':cube[s-1].tolist(),'plan_count':len(active),'segment_kind':kind})
        probe.update(steps=steps,step_dt_s=dt,frames=new_frames,actual_eef_positions_m=eef.tolist())
        probe['capture_reconciliation']={'recorded_frames_crosschecked':len(original_frames),
            'rendered_frames':len(files),'alignment_max_allowed_error_m':1e-6,
            'source':'Live capture files + HDF5 states/observations; missing final snapshot reconstructed after simulator process exit.',
            'skill_curve_scope':'The persisted numeric snapshot includes only the first skill segment. Rendered blue curves show skill references already generated at each frame, retaining their history; complete executed TCP states come from HDF5.'}
    (folder/'probe-recovered.json').write_text(json.dumps(probe,indent=2))
    hashes=json.loads((folder/'source-sha256.json').read_text())
    changed=[p for p,digest in hashes.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=digest]
    stability={'unchanged':not changed,'changed_paths':changed,'checked_at':'post-run HDF5/frame reconciliation'}
    (folder/'source-stability.json').write_text(json.dumps(stability,indent=2))
    assert not changed, changed
    print(json.dumps({'case':name,'steps':steps,'frames':len(files),'crosschecked':len(original_frames)}))
