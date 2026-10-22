# SPDX-FileCopyrightText: 2026
# SPDX-License-Identifier: MIT
"""Physical RGB sorting with an idealized Cartesian parallel gripper in MuJoCo.

The measured native mini dining-table bounding box supplies the support plane.
Only the table and gripper/cube contacts are simulated; household geometry is a
render-only Blender reference. No attachments or cube pose writes after reset.
"""
import argparse, hashlib, json
from pathlib import Path
import mujoco
import numpy as np


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seed',type=int,default=7)
    a=p.parse_args(); a.output.mkdir(parents=True,exist_ok=False)
    rng=np.random.default_rng(a.seed)
    colors=['red','green','blue']
    starts=np.array([[.48,.17,.022],[.64,.08,.022],[.47,-.06,.022]])
    starts[:,:2]+=rng.uniform(-.018,.018,(3,2))
    goals=np.array([[.39,-.25,.022],[.58,-.25,.022],[.77,-.25,.022]])
    cubes=''.join(f'<body name="{c}" pos="{x} {y} {z}"><freejoint/><geom name="{c}_geom" type="box" size=".022 .022 .022" mass=".05" rgba="{rgb} 1" friction="1.6 .01 .001"/></body>' for c,(x,y,z),rgb in zip(colors,starts,['.9 .04 .03','.03 .75 .12','.03 .2 .95']))
    xml=f'''<mujoco model="mini_rgb_sort"><option timestep="0.0016666666666666668" integrator="implicitfast" iterations="80"/><default><geom solref=".006 1" solimp=".95 .99 .001" friction="1.4 .01 .001" condim="4"/><joint damping="5"/></default><worldbody>
    <geom name="native_table_proxy" type="box" size=".675392 .442032 .025" pos=".558701 -.011005 -.025"/>
    {cubes}
    <body name="hand"><joint name="x" type="slide" axis="1 0 0"/><joint name="y" type="slide" axis="0 1 0"/><joint name="z" type="slide" axis="0 0 1"/>
    <geom type="box" size=".045 .055 .018" pos="0 0 .085" mass=".3"/>
    <body name="left" pos="0 .042 0"><joint name="close_left" type="slide" axis="0 -1 0" range="0 .024"/><geom type="box" size=".014 .006 .03" pos="0 0 .015" mass=".04"/></body>
    <body name="right" pos="0 -.042 0"><joint name="close_right" type="slide" axis="0 1 0" range="0 .024"/><geom type="box" size=".014 .006 .03" pos="0 0 .015" mass=".04"/></body>
    </body></worldbody><actuator><position joint="x" kp="3000" kv="90"/><position joint="y" kp="3000" kv="90"/><position joint="z" kp="3000" kv="90"/><position joint="close_left" kp="450" kv="4" forcerange="-12 12"/><position joint="close_right" kp="450" kv="4" forcerange="-12 12"/></actuator></mujoco>'''
    (a.output/'model.xml').write_text(xml)
    m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m)
    ids=[mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_BODY,c) for c in colors]
    hand=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_BODY,'hand')
    ji=[mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_JOINT,n) for n in ['x','y','z','close_left','close_right']]
    qi=m.jnt_qposadr[ji]
    d.qpos[qi[:3]]=[.35,0,.25];d.ctrl[:3]=[.35,0,.25]
    mujoco.mj_forward(m,d)
    records=[]; phases=[]; measured=[]
    def run(name,seconds,target,closing):
        begin=d.ctrl[:3].copy(); target=np.asarray(target)
        frames=round(seconds*30)
        for f in range(frames):
            alpha=min((f+1)/max(frames*.8,1),1);alpha=alpha*alpha*(3-2*alpha)
            d.ctrl[:3]=begin*(1-alpha)+target*alpha;d.ctrl[3:]=closing
            for _ in range(20):mujoco.mj_step(m,d)
            records.append(dict(hand=d.xpos[hand].tolist(),fingers=d.qpos[qi[3:]].tolist(),cubes=d.xpos[ids].tolist(),quat=d.xquat[ids].tolist(),phase=name,contact_count=int(d.ncon),time=float(d.time)))
        phases.append(dict(name=name,end_frame=len(records)))
    run('initialize',.5,[.35,0,.25],0)
    for i,c in enumerate(colors):
        xyz=d.xpos[ids[i]].copy();src=xyz[:2];g=goals[i,:2]
        run(c+'_approach',1.0,[*src,.21],0)
        run(c+'_descend',.7,[*src,.024],0)
        run(c+'_grasp',.6,[*src,.024],.024)
        before=float(d.xpos[ids[i],2]);run(c+'_lift',.8,[*src,.22],.024)
        lifted=float(d.xpos[ids[i],2]-before)
        run(c+'_transfer',1.1,[*g,.22],.024)
        run(c+'_lower',.7,[*g,.026],.024)
        run(c+'_release',.5,[*g,.026],0)
        run(c+'_retreat',.7,[*g,.23],0)
        measured.append(dict(color=c,lift_m=lifted))
    run('settle',1.0,[.3,.12,.26],0)
    final=d.xpos[ids].copy(); errors=np.linalg.norm(final[:,:2]-goals[:,:2],axis=1)
    success=bool(all(x['lift_m']>.12 for x in measured) and (errors<.035).all() and (abs(final[:,2]-.022)<.01).all())
    result=dict(success=success,seed=a.seed,frames=len(records),display_fps=30,physics_dt=1/600,physics_substeps_per_frame=20,physical_seconds=float(d.time),display_seconds=len(records)/30,starts=starts.tolist(),goals=goals.tolist(),final=final.tolist(),xy_errors_m=errors.tolist(),lifts=measured,phases=phases,contact_steps=sum(r['contact_count']>0 for r in records),model='idealized Cartesian parallel gripper; MuJoCo rigid contacts; no cube attachment',scene='World-SimReady-Home-mini scene000430; measured native dining-table proxy only in physics; full house render only',source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),mujoco_version=mujoco.__version__)
    (a.output/'trajectory.json').write_text(json.dumps(records))
    (a.output/'verification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
    assert success,'Physical grasp/sort failed; outputs preserved'

if __name__=='__main__':main()
