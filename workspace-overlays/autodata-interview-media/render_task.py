# SPDX-FileCopyrightText: 2026
# SPDX-License-Identifier: MIT
"""Render measured MuJoCo gripper/cube states inside immutable mini geometry.

Blender materials are illustrative replacements for source MDL. The robot is an
idealized Cartesian gripper, with decorative rails; this is not AutoData inference.
"""
import argparse, hashlib, json, math, sys
from pathlib import Path
import bpy
from mathutils import Vector, Quaternion

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--scene',type=Path,required=True);p.add_argument('--trajectory',type=Path,required=True)
p.add_argument('--output',type=Path,required=True);p.add_argument('--view',choices=['detail','wide','top'],default='detail')
p.add_argument('--style',choices=['neutral','warm','cool','dark','wood'],default='neutral')
p.add_argument('--foreground',action='store_true');p.add_argument('--engine',choices=['CYCLES','BLENDER_EEVEE'],default='BLENDER_EEVEE');p.add_argument('--stride',type=int,default=3);p.add_argument('--preview',action='store_true')
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);a.output.mkdir(parents=True,exist_ok=False)
bpy.ops.wm.open_mainfile(filepath=str(a.scene))
home_objects=list(bpy.context.scene.objects)
# Shift all imported roots together; preserve native relative geometry.
for obj in list(bpy.context.scene.objects):
 if obj.parent is None:obj.location+=Vector((-22.35,4.75,-.75))
for obj in bpy.data.objects:
 ancestors=[];q=obj
 while q:
  ancestors.append(q.name.lower());q=q.parent
 text='/'.join(ancestors)
 if any(x in text for x in ['ceiling','ornament_1441482','ornament_1437192','ornament_1433619','diningchair']):obj.hide_render=True
 # Large source wall assemblies can obstruct the close-up from outside the room.
 if obj.type=='MESH' and obj.name.startswith('wall_'):
  coords=[obj.matrix_world@Vector(c) for c in obj.bound_box]
  if min(v.z for v in coords)>1.8:obj.hide_render=True

s=bpy.context.scene;s.render.engine=a.engine;s.cycles.samples=8;s.cycles.use_denoising=True
s.cycles.device='GPU'
s.eevee.taa_render_samples=16
prefs=bpy.context.preferences.addons['cycles'].preferences
try:
 prefs.compute_device_type='OPTIX';prefs.get_devices()
 for dev in prefs.devices:dev.use=dev.type=='OPTIX'
except Exception:s.cycles.device='CPU'
s.render.resolution_x=1280;s.render.resolution_y=720;s.render.resolution_percentage=100
s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGB'
s.render.film_transparent=False;s.view_settings.view_transform='AgX'
s.world=bpy.data.worlds.new('interview_world');s.world.use_nodes=True
s.world.node_tree.nodes.clear()
bg=s.world.node_tree.nodes.new('ShaderNodeBackground');wo=s.world.node_tree.nodes.new('ShaderNodeOutputWorld');s.world.node_tree.links.new(bg.outputs[0],wo.inputs[0])
bg.inputs['Color'].default_value=(.65,.72,.85,1);bg.inputs['Strength'].default_value=.5

def mat(name,color,metal=0,rough=.5):
 m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
 m.node_tree.nodes.clear();b=m.node_tree.nodes.new('ShaderNodeBsdfPrincipled');mo=m.node_tree.nodes.new('ShaderNodeOutputMaterial');m.node_tree.links.new(b.outputs[0],mo.inputs[0]);b.inputs['Base Color'].default_value=(*color,1);b.inputs['Metallic'].default_value=metal;b.inputs['Roughness'].default_value=rough
 return m
white=mat('gripper_porcelain',(.68,.74,.79),.3,.25)
black=mat('rubber_fingers',(.035,.045,.055),.15,.38)
metal=mat('rail_aluminium',(.16,.20,.24),.75,.28)
cyan=mat('controller_accent',(.02,.52,.70),.3,.25)
cols=[(.8,.025,.025),(.025,.6,.09),(.025,.14,.85)]
cm=[mat(n,c,.1,.27) for n,c in zip(['red','green','blue'],cols)]
# All MDL-derived materials are replaced by explicit neutral approximations.
for m in list(bpy.data.materials):
 if m in [white,black,metal,cyan,*cm]:continue
 color=tuple(m.diffuse_color[:3])
 if max(color)-min(color)<.03:color=(.72,.70,.65)
 m.use_nodes=True;b=m.node_tree.nodes.get('Principled BSDF')
 if b:b.inputs['Base Color'].default_value=(*color,1);b.inputs['Roughness'].default_value=.6
# Keep original table mesh with an explicit, reproducible display material.
table=bpy.data.objects.get('mesh059')
tm=mat('table_display',(.12,.07,.035) if a.style=='wood' else (.055,.065,.075),.15,.35)
if table:table.data.materials.clear();table.data.materials.append(tm)

def box(name,loc,size,material,bevel=.002):
 bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.name=name;o.dimensions=size
 bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 if material:o.data.materials.append(material)
 if bevel:
  mod=o.modifiers.new('soft_edges','BEVEL');mod.width=bevel;mod.segments=3;o.modifiers.new('weighted_normals','WEIGHTED_NORMAL')
 return o
cubes=[box(n,(0,0,0),(.044,)*3,m,.003) for n,m in zip(['R','G','B'],cm)]
goals=[[.39,-.25,.001],[.58,-.25,.001],[.77,-.25,.001]]
for n,xyz,m in zip(['R','G','B'],goals,cm):
 # Outlined target pads, uncollidable visual guides, below the cube support surface.
 for dx,dy,sx,sy in [(0,-.04,.084,.003),(0,.04,.084,.003),(-.04,0,.003,.084),(.04,0,.003,.084)]:box('target_'+n,(xyz[0]+dx,xyz[1]+dy,.001),(sx,sy,.001),m,0)
 # Table labels sit toward camera.
 bpy.ops.object.text_add(location=(xyz[0]-.017,xyz[1]-.085,.002));o=bpy.context.object;o.data.body=n;o.data.size=.045;o.data.extrude=.0001;o.data.materials.append(m)
palm=box('palm',(0,0,0),(.09,.11,.036),white)
fingers=[box('finger_'+str(i),(0,0,0),(.028,.012,.06),black) for i in range(2)]
accent=box('accent',(0,0,0),(.07,.085,.006),cyan)
# Decorative Cartesian support; only gripper and table/cubes are in the physics model.
box('column',(-.04,.34,.27),(.07,.07,.54),metal)
box('mount',(-.04,.34,.015),(.16,.16,.03),black)
xrail=box('x_rail',(.43,.34,.55),(.98,.035,.035),metal)
yrail=box('y_rail',(0,0,.55),(.035,.72,.035),metal)
zrail=box('z_rail',(0,0,0),(.018,.018,.3),metal)

def light(name,loc,power,size,color):
 d=bpy.data.lights.new(name,'AREA');d.energy=power;d.shape='DISK';d.size=size;d.color=color
 o=bpy.data.objects.new(name,d);s.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector((.5,0,0))-o.location).to_track_quat('-Z','Y').to_euler()
 return d
keycol=(1,.73,.48) if a.style=='warm' else ((.55,.75,1) if a.style=='cool' else (1,.95,.85))
light('key',(1,-.5,2),180 if a.style=='dark' else 450,2,keycol)
light('fill',(-.5,.1,1.5),180,1.5,(.7,.85,1))
camd=bpy.data.cameras.new('camera');cam=bpy.data.objects.new('camera',camd);s.collection.objects.link(cam);s.camera=cam
pos,look,lens={'detail':((1.25,-1.35,1.0),(.49,-.015,.17),48),'wide':((1.65,-1.9,1.55),(.4,0,.28),35),'top':((.55,-.1,2.1),(.55,-.1,0),48)}[a.view]
cam.location=pos;cam.rotation_euler=(Vector(look)-cam.location).to_track_quat('-Z','Y').to_euler();camd.lens=lens
traj=json.loads(a.trajectory.read_text())
indices=[0,120,183,380,593] if a.preview else list(range(0,len(traj),a.stride))
animated=[palm,accent,*fingers,yrail,zrail,*cubes]
for sequence,i in enumerate(indices):
 r=traj[i];x,y,z=r['hand'];cl,cr=r['fingers']
 palm.location=(x,y,z+.085);accent.location=(x,y,z+.106)
 fingers[0].location=(x,y+.042-cl,z+.015);fingers[1].location=(x,y-.042+cr,z+.015)
 yrail.location=(x,-.02,.55);height=max(.01,.55-z-.105);zrail.location=(x,y,(.55+z+.105)/2);zrail.scale.z=height/.3
 for o,xyz,q in zip(cubes,r['cubes'],r['quat']):o.location=xyz;o.rotation_mode='QUATERNION';o.rotation_quaternion=Quaternion(q)
 for o in animated:
  o.keyframe_insert(data_path='location',frame=sequence);o.keyframe_insert(data_path='scale',frame=sequence)
  if o.rotation_mode=='QUATERNION':o.keyframe_insert(data_path='rotation_quaternion',frame=sequence)
if a.foreground:
 for o in home_objects:
  if o!=table:o.hide_render=True
 s.render.film_transparent=True;s.render.image_settings.color_mode='RGBA'
s.frame_start=0;s.frame_end=len(indices)-1;s.render.filepath=str(a.output/'frame_')
bpy.ops.render.render(animation=True)
(a.output/'render.json').write_text(json.dumps(dict(view=a.view,style=a.style,source_frames=indices,physics_trajectory_sha256=hashlib.sha256(a.trajectory.read_bytes()).hexdigest(),scene_file_sha256=hashlib.sha256(a.scene.read_bytes()).hexdigest(),render=a.engine+'; replacement display materials; idealized gripper; full household geometry render only',blender=bpy.app.version_string),indent=2))
