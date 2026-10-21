# SPDX-FileCopyrightText: 2026
# SPDX-License-Identifier: MIT
"""Render official G1-D meshes at measured MuJoCo body poses inside mini home."""
import argparse,hashlib,json,sys,xml.etree.ElementTree as ET
from pathlib import Path
import bpy
from mathutils import Vector,Quaternion,Matrix
p=argparse.ArgumentParser(description=__doc__)
for name in ['scene','urdf','trajectory','verification','output']:p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--view',choices=['wide','detail','side'],default='wide');p.add_argument('--preview',action='store_true');p.add_argument('--stride',type=int,default=3)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);a.output.mkdir(parents=True,exist_ok=False)
bpy.ops.wm.open_mainfile(filepath=str(a.scene))
for obj in list(bpy.context.scene.objects):
 if obj.parent is None:obj.location+=Vector((-22.35,4.75,-.75))
for obj in bpy.data.objects:
 parts=[];q=obj
 while q:parts.append(q.name.lower());q=q.parent
 if any(t in '/'.join(parts) for t in ['ceiling','ornament_1441482','ornament_1437192','ornament_1433619','diningchair']):obj.hide_render=True
s=bpy.context.scene;s.render.engine='BLENDER_EEVEE';s.eevee.taa_render_samples=24
s.render.resolution_x=1280;s.render.resolution_y=720;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGB';s.view_settings.view_transform='AgX'
s.world=bpy.data.worlds.new('task_world');s.world.use_nodes=True;nt=s.world.node_tree;nt.nodes.clear();bg=nt.nodes.new('ShaderNodeBackground');out=nt.nodes.new('ShaderNodeOutputWorld');nt.links.new(bg.outputs[0],out.inputs[0]);bg.inputs[0].default_value=(.65,.75,.9,1);bg.inputs[1].default_value=.5

def mat(name,color,metal=0,rough=.4):
 m=bpy.data.materials.new(name);m.use_nodes=True;nt=m.node_tree;nt.nodes.clear();b=nt.nodes.new('ShaderNodeBsdfPrincipled');o=nt.nodes.new('ShaderNodeOutputMaterial');nt.links.new(b.outputs[0],o.inputs[0]);b.inputs['Base Color'].default_value=(*color,1);b.inputs['Metallic'].default_value=metal;b.inputs['Roughness'].default_value=rough;return m
met=mat('robot_silver',(.46,.52,.6),.55,.3);dark=mat('robot_dark',(.03,.035,.04),.1,.4);white=mat('robot_white',(.72,.76,.8),.25,.35)
verify=json.loads(a.verification.read_text())
robot=[]
for link in ET.parse(a.urdf).getroot().findall('link'):
 v=link.find('visual')
 if v is None:continue
 mesh=v.find('geometry/mesh')
 if mesh is None:continue
 bpy.ops.wm.stl_import(filepath=str((a.urdf.parent/mesh.attrib['filename']).resolve()));o=bpy.context.object;o.name='G1D_'+link.attrib['name']
 color=v.find('material/color');rgba=[.7]*3 if color is None else list(map(float,color.attrib['rgba'].split()))[:3]
 o.data.materials.clear();o.data.materials.append(dark if sum(rgba)<1.3 else (met if link.attrib['name'].startswith(('AGV','LZ','Pitch','Yaw')) else white))
 for poly in o.data.polygons:poly.use_smooth=True
 if verify.get('gripper')=='parallel' and link.attrib['name'].startswith('right_hand_'):o.hide_render=True
 robot.append((o,link.attrib['name']))
if verify.get('gripper')=='parallel':
 for name,loc,size,material in [('demo_adapter',(-.11,0,0),(.07,.024,.024),met),('demo_gripper',(-.075,0,0),(.036,.104,.08),met),('demo_jaw_left',(-.015,0,0),(.06,.012,.028),dark),('demo_jaw_right',(-.015,0,0),(.06,.012,.028),dark)]:
  bpy.ops.mesh.primitive_cube_add(size=1);o=bpy.context.object;o.name=name;o.dimensions=size;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.transform(Matrix.Translation(loc));o.data.materials.append(material);robot.append((o,'demo_gripper' if name=='demo_adapter' else name))
cols=[(.8,.025,.025),(.025,.6,.09),(.025,.14,.85)];cm=[mat(n,c,.1,.3) for n,c in zip(['red','green','blue'],cols)]
cubes=[]
for n,m in zip(['R','G','B'],cm):
 bpy.ops.mesh.primitive_cube_add(size=.044);o=bpy.context.object;o.name='cube_'+n;o.data.materials.append(m);be=o.modifiers.new('edges','BEVEL');be.width=.002;be.segments=3;cubes.append(o)
for x,m,n in zip([.48,.58,.68],cm,['R','G','B']):
 for dx,dy,sx,sy in [(0,-.034,.07,.002),(0,.034,.07,.002),(-.034,0,.002,.07),(.034,0,.002,.07)]:
  bpy.ops.mesh.primitive_cube_add(size=1,location=(x+dx,-.21+dy,.001));o=bpy.context.object;o.dimensions=(sx,sy,.001);o.data.materials.append(m)
table=bpy.data.objects.get('mesh059')
if table:table.data.materials.clear();table.data.materials.append(mat('table_display',(.055,.065,.075),.15,.4))
for loc,power,color in [((1,-.4,2.4),350,(1,.92,.8)),((-.7,-1,1),150,(.7,.85,1))]:
 d=bpy.data.lights.new('area','AREA');d.energy=power;d.size=2;d.color=color;o=bpy.data.objects.new('area',d);s.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector((.55,-.25,.1))-o.location).to_track_quat('-Z','Y').to_euler()
d=bpy.data.cameras.new('camera');cam=bpy.data.objects.new('camera',d);s.collection.objects.link(cam);s.camera=cam
pos,target,lens={'wide':((1.75,-2.05,1.25),(.48,-.30,-.05),40),'detail':((1.15,-1.25,.82),(.56,-.25,.12),52),'side':((1.9,-.7,.9),(.5,-.28,.02),48)}[a.view]
cam.location=pos;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();d.lens=lens
traj=json.loads(a.trajectory.read_text());verify=json.loads(a.verification.read_text());names=verify['body_names'];byname={n:i for i,n in enumerate(names)}
indices=[0,min(100,len(traj)-1),min(155,len(traj)-1),len(traj)-1] if a.preview else list(range(0,len(traj),a.stride))
for f,idx in enumerate(indices):
 r=traj[idx]
 for o,n in robot:
  i=byname[n];o.location=r['body_pos'][i];o.rotation_mode='QUATERNION';o.rotation_quaternion=Quaternion(r['body_quat'][i]);o.keyframe_insert(data_path='location',frame=f);o.keyframe_insert(data_path='rotation_quaternion',frame=f)
 for o,pos,q in zip(cubes,r['cubes'],r['cube_quat']):
  o.location=pos;o.rotation_mode='QUATERNION';o.rotation_quaternion=Quaternion(q);o.keyframe_insert(data_path='location',frame=f);o.keyframe_insert(data_path='rotation_quaternion',frame=f)
s.frame_start=0;s.frame_end=len(indices)-1;s.render.filepath=str(a.output/'frame_');bpy.ops.render.render(animation=True)
(a.output/'render.json').write_text(json.dumps(dict(view=a.view,source_frames=indices,model='Official Unitree G1-D URDF; meshes positioned from MuJoCo body poses',trajectory_sha256=hashlib.sha256(a.trajectory.read_bytes()).hexdigest(),task_count=len(verify['checks']),task_success=verify['success'],display_materials='Blender replacements for mini MDL and explicit robot silver/white/dark'),indent=2))
