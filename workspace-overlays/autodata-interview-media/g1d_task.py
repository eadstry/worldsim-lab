# SPDX-FileCopyrightText: 2026
# SPDX-License-Identifier: MIT
"""Attempt contact-driven native G1-D Dex3 grasp/sort using the official URDF.

Fixed mobile base, gravity compensation and scripted bounded IK; source mesh
collisions for the right hand, table bounding-box proxy, no house/self collision.
No learned policy or AutoData augmentation is claimed.
"""
import argparse,hashlib,json,xml.etree.ElementTree as ET
from pathlib import Path
import mujoco,numpy as np
from g1d_kinematics import Robot

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiled',type=Path,required=True);p.add_argument('--urdf',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--gripper',choices=['native','parallel'],default='native');p.add_argument('--jitter',type=float,default=0);p.add_argument('--seed',type=int,default=7);p.add_argument('--count',type=int,choices=[1,3],default=1);p.add_argument('--offset-x',type=float,default=.13);p.add_argument('--offset-y',type=float,default=.065);p.add_argument('--close',type=float,default=.65)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
r=Robot(a.urdf,base=(.42,-.48,-.60));r.offset=np.array([a.offset_x,a.offset_y,0.]);root=ET.parse(a.compiled).getroot()
ET.SubElement(root,'option',dict(timestep=str(1/1200),integrator='implicitfast',iterations='60'))
world=root.find('worldbody');base=world.find('body');base.set('pos','.42 -.48 -.60');base.set('quat','.707106781 0 0 .707106781')
for body in base.iter('body'):
 for geom in body.findall('geom'):
  active=a.gripper=='native' and body.attrib.get('name','').startswith('right_hand') and geom.attrib.get('group','0')!='1'
  geom.set('contype','1' if active else '0');geom.set('conaffinity','2' if active else '0');geom.set('friction','1.8 .02 .001');geom.set('condim','4')
if a.gripper=='parallel':
 palm=next(b for b in base.iter('body') if b.attrib['name']=='right_hand_palm_link')
 tool=ET.SubElement(palm,'body',dict(name='demo_gripper',pos=f'{a.offset_x} {a.offset_y} 0'))
 ET.SubElement(tool,'geom',dict(name='demo_palm',type='box',pos='-.075 0 0',size='.018 .052 .04',mass='.18',contype='0',conaffinity='0'))
 for sign,name in [(1,'left'),(-1,'right')]:
  finger=ET.SubElement(tool,'body',dict(name='demo_jaw_'+name,pos=f'0 {sign*.042} 0'))
  ET.SubElement(finger,'joint',dict(name='demo_close_'+name,type='slide',axis=f'0 {-sign} 0',range='0 .024',actuatorfrcrange='-12 12'))
  ET.SubElement(finger,'geom',dict(name='demo_pad_'+name,type='box',pos='-.015 0 0',size='.03 .006 .014',mass='.04',contype='1',conaffinity='2',friction='1.8 .02 .001',condim='4'))
for joint in base.iter('joint'):
 joint.set('damping','.08' if '_hand_' in joint.attrib['name'] else '3');joint.set('armature','.01' if '_hand_' in joint.attrib['name'] else '.1')
ET.SubElement(world,'geom',dict(name='native_table_proxy',type='box',size='.675392 .442032 .025',pos='.558701 -.011005 -.025',contype='2',conaffinity='3',friction='1.5 .01 .001'))
colors=['red','green','blue'];starts=np.array([[.68,-.32,.022],[.48,-.32,.022],[.58,-.32,.022]]) if a.gripper=='parallel' else np.array([[.48,-.32,.022],[.58,-.32,.022],[.68,-.32,.022]]);goals=np.array([[.48,-.21,.022],[.58,-.21,.022],[.68,-.21,.022]])
starts[:,:2]+=np.random.default_rng(a.seed).uniform(-a.jitter,a.jitter,(3,2))
for c,xyz in zip(colors,starts):
 b=ET.SubElement(world,'body',dict(name='cube_'+c,pos=' '.join(map(str,xyz))));ET.SubElement(b,'freejoint');ET.SubElement(b,'geom',dict(name='cube_'+c,type='box',size='.022 .022 .022',mass='.05',contype='2',conaffinity='3',friction='1.8 .02 .001',condim='4'))
act=ET.SubElement(root,'actuator');jn=[]
for joint in base.iter('joint'):
 name=joint.attrib['name'];jn.append(name);finger='_hand_' in name or 'demo_close' in name;slide=joint.attrib.get('type')=='slide'
 ET.SubElement(act,'position',dict(name=name,joint=name,kp=('350' if name.startswith('demo_close') else '25') if finger else ('3000' if slide else '500'),kv=('2' if name.startswith('demo_close') else '.3') if finger else ('80' if slide else '12')))
xml=a.output/'task.xml';ET.ElementTree(root).write(xml)
m=mujoco.MjModel.from_xml_path(str(xml.resolve()));d=mujoco.MjData(m)
ji=[mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_JOINT,n) for n in jn];qi=m.jnt_qposadr[ji];di=m.jnt_dofadr[ji]
initial_arm,_=r.ik(np.array([.68 if a.gripper=='parallel' else .48,-.32,.2]),np.array([.595,-.19,.279,-.384,1.659,-.167,-1.34]))
q0={**r.fixed,**dict(zip(r.names,initial_arm))}
for name in jn:
 if name.startswith('right_hand_thumb_1'):q0[name]=.45
 if name.startswith('right_hand_thumb_2'):q0[name]=0
for k,name in enumerate(jn):d.qpos[qi[k]]=q0.get(name,0);d.ctrl[k]=q0.get(name,0)
mujoco.mj_forward(m,d)
bi=[mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_BODY,'cube_'+c) for c in colors]
records=[];checks=[];last=np.array([q0[x] for x in r.names]);ikerrors=[]

def run(name,seconds,target,grasp):
 global last
 if target is not None:
  last,err=r.ik(np.asarray(target),last)
  if err>.005:
   for trial in range(4):
    alternative,ae=r.ik(np.asarray(target),np.random.default_rng(trial).uniform(r.lo+.01,r.hi-.01))
    if ae<err:last,err=alternative,ae
    if err<.001:break
  ikerrors.append(dict(phase=name,error_m=err))
  qmap=dict(zip(r.names,last))
 else:qmap={}
 qgoal=d.ctrl.copy()
 for k,n in enumerate(jn):
  if n in qmap:qgoal[k]=qmap[n]
  if n.startswith('demo_close'):qgoal[k]=.024 if grasp else 0
  if n.startswith('right_hand_'):
   if 'thumb_0' in n:qgoal[k]=0
   elif 'thumb_1' in n:qgoal[k]=-.5 if grasp else .45
   elif 'thumb_2' in n:qgoal[k]=-.6 if grasp else 0
   else:qgoal[k]=(a.close if grasp else .3) if '_0_' in n else (.9 if grasp else .9)
 begin=d.ctrl.copy()
 for f in range(round(seconds*30)):
  alpha=min((f+1)/(seconds*30*.75),1);alpha=alpha*alpha*(3-2*alpha);d.ctrl[:]=begin*(1-alpha)+qgoal*alpha
  for _ in range(40):
   d.qfrc_applied[:]=0;d.qfrc_applied[di]=d.qfrc_bias[di];mujoco.mj_step(m,d)
   assert np.max(np.abs(d.qacc))<1e7,'Unstable dynamics'
  assert np.isfinite(d.qpos).all()
  contacts=[]
  for con in d.contact:
   g1,g2=int(con.geom1),int(con.geom2)
   contacts.append([mujoco.mj_id2name(m,mujoco.mjtObj.mjOBJ_GEOM,g1),mujoco.mj_id2name(m,mujoco.mjtObj.mjOBJ_GEOM,g2)])
  records.append(dict(phase=name,time=float(d.time),body_pos=d.xpos.tolist(),body_quat=d.xquat.tolist(),joints={n:float(d.qpos[q]) for n,q in zip(jn,qi)},cubes=d.xpos[bi].tolist(),cube_quat=d.xquat[bi].tolist(),contacts=contacts))
 print(name,d.xpos[bi].round(4).tolist(),flush=True)
run('initialize',.8,[.68 if a.gripper=='parallel' else .48,-.32,.2],False)
for i,c in enumerate(colors[:a.count]):
 xyz=d.xpos[bi[i]].copy();src=xyz[:2];g=goals[i,:2]
 run(c+'_approach',1.2,[*src,.20],False);run(c+'_descend',1.1,[*src,.025],False);run(c+'_grasp',1,[*src,.025],True)
 before=d.xpos[bi[i],2];run(c+'_lift',1.3,[*src,.20],True);lift=float(d.xpos[bi[i],2]-before)
 run(c+'_transfer',1.6,[*g,.20],True);run(c+'_lower',1.1,[*g,.025],True);run(c+'_release',.8,[*g,.025],False);run(c+'_retreat',1.2,[*g,.2],False)
 checks.append(dict(color=c,lift_m=lift,final=d.xpos[bi[i]].tolist(),error_xy=float(np.linalg.norm(d.xpos[bi[i],:2]-g))))
run('settle',1,None,False)
summary=dict(seed=a.seed,starts=starts.tolist(),goals=goals.tolist(),gripper=a.gripper,success=all(x['lift_m']>.1 and x['error_xy']<.035 for x in checks),checks=checks,frames=len(records),fps=30,body_names=[mujoco.mj_id2name(m,mujoco.mjtObj.mjOBJ_BODY,i) for i in range(m.nbody)],ik=ikerrors,base=r.base.tolist(),limitations=['Fixed mobile base; '+('custom parallel-gripper adaptation replaces native Dex3 contacts' if a.gripper=='parallel' else 'native Dex3 convex mesh contacts')+'; non-hand robot/self and house collisions disabled','Scripted bounded IK, ideal gravity compensation; not official policy or AutoData generation','Native table approximated by measured bounding-box support; full house render only'],urdf_sha256=hashlib.sha256(a.urdf.read_bytes()).hexdigest(),mujoco=mujoco.__version__)
(a.output/'trajectory.json').write_text(json.dumps(records));(a.output/'verification.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2));assert summary['success'],'Native G1-D contact grasp failed; diagnostic states retained'
