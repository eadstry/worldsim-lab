"""Render every recorded pre-action state in the original textured mini home."""
import argparse, json, sys, time
from pathlib import Path
import bpy, numpy as np
from mathutils import Vector, Quaternion, Matrix
sys.path.insert(0, str(Path(__file__).resolve().parent))
from geometry import compose_visual_frames
p = argparse.ArgumentParser()
p.add_argument('--episode', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
p.add_argument('--preview', action='store_true')
p.add_argument('--diagnostic', action='store_true')
p.add_argument('--samples', type=int, default=24)
p.add_argument('--condition', type=int, default=0)
p.add_argument('--width', type=int, default=1920)
p.add_argument('--height', type=int, default=1080)
p.add_argument('--frame-index', type=int, default=-1)
p.add_argument('--view', choices=['task', 'wide'], default='task')
p.add_argument('--engine', choices=['CYCLES', 'BLENDER_EEVEE'], default='CYCLES')
a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
a.out.mkdir(parents=True, exist_ok=False)
r = np.load(a.episode / 'trajectory.npz')
info = json.loads((a.episode / 'verification.json').read_text())
assert info['success'] or a.diagnostic, 'Refuse failed trajectory'
for o in list(bpy.context.scene.objects):
    if o.parent is None:
        o.location += Vector((-22.35, 4.75, -0.75))
for o in bpy.data.objects:
    chain = []
    q = o
    while q:
        chain.append(q.name.lower())
        q = q.parent
    if any((n in '/'.join(chain) for n in ['ornament_1441482', 'ornament_1437192', 'ornament_1433619', 'diningchair'])):
        o.hide_render = True
s = bpy.context.scene
s.render.engine = 'CYCLES'
s.cycles.samples = a.samples
s.cycles.use_denoising = True
s.cycles.device = 'GPU'
s.render.use_persistent_data = True
prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type = 'OPTIX'
prefs.get_devices()
for d in prefs.devices:
    d.use = d.type == 'OPTIX'
if a.engine == 'BLENDER_EEVEE':
    s.render.engine = a.engine
    s.eevee.taa_render_samples = a.samples
    s.eevee.use_raytracing = True
s.render.resolution_x = a.width
s.render.resolution_y = a.height
s.render.resolution_percentage = 100
s.view_settings.view_transform = 'AgX'
s.view_settings.exposure = -0.35
s.render.image_settings.file_format = 'PNG'
s.render.image_settings.color_mode = 'RGB'
s.render.fps = 30
s.world = bpy.data.worlds.new('native_home_ambient')
s.world.use_nodes = True
nt = s.world.node_tree
bg = nt.nodes.new('ShaderNodeBackground')
wo = nt.nodes.new('ShaderNodeOutputWorld')
nt.links.new(bg.outputs[0], wo.inputs[0])
bg.inputs[0].default_value = (0.55, 0.68, 0.9, 1)
bg.inputs[1].default_value = 0.1

def mat(name, c, metal=0, rough=0.35):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    b = nt.nodes.new('ShaderNodeBsdfPrincipled')
    o = nt.nodes.new('ShaderNodeOutputMaterial')
    o.is_active_output = True
    nt.links.new(b.outputs[0], o.inputs[0])
    b.inputs['Base Color'].default_value = (*c, 1)
    b.inputs['Metallic'].default_value = metal
    b.inputs['Roughness'].default_value = rough
    return m
materials = {}
data = np.load(a.episode / 'visual_meshes.npz')
meshdata = {}
geoms = json.loads((a.episode / 'visual_geoms.json').read_text())
objects = []
for g in geoms:
    key = g['mesh']
    srgb = g['rgba'][:3]
    color = tuple((c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb))
    dark = sum(srgb) < 0.8
    is_shell = info['robot'] == 'g1d' and any((n in g['body_name'] for n in ['torso', 'shoulder', 'AGV', 'LZ_', 'head']))
    materialkey = (color, dark, is_shell)
    if materialkey not in materials:
        materials[materialkey] = mat('native_CAD_' + str(len(materials)), color, 0 if info['robot'] == 'so101' or dark else 0.1 if is_shell else 0.55, 0.38 if info['robot'] == 'so101' or is_shell else 0.29)
    if key not in meshdata:
        mesh = bpy.data.meshes.new(key)
        mesh.from_pydata(data[key + '_vertices'].tolist(), [], data[key + '_faces'].tolist())
        mesh.update()
        meshdata[key] = mesh
    mesh = meshdata[key].copy()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    mesh.set_sharp_from_angle(angle=0.6)
    mesh.materials.append(materials[materialkey])
    o = bpy.data.objects.new(g['body_name'], mesh)
    s.collection.objects.link(o)
    local = Matrix.Translation(g['pos']) @ Quaternion(g['quat']).to_matrix().to_4x4()
    objects.append((o, g['body'], local))
colors = [(0.65, 0.012, 0.008), (0.01, 0.4, 0.025), (0.008, 0.04, 0.65)]
cm = [mat(n, c, 0, 0.3) for n, c in zip(['red', 'green', 'blue'], colors)]
cubes = []
for i, (c, material) in enumerate(zip(['red', 'green', 'blue'], cm)):
    bpy.ops.mesh.primitive_cube_add(size=info['cfg']['half'] * 2)
    o = bpy.context.object
    o.name = 'task_cube_' + c
    o.data.materials.append(material)
    be = o.modifiers.new('machined_edge', 'BEVEL')
    be.width = 0.0008
    be.segments = 3
    bid = info['body_names'].index('cube_' + c)
    objects.append((o, bid, Matrix.Identity(4)))
for pos, material in zip(info['goals'], cm):
    h = info['cfg']['half'] + (0.035 if info['robot'] == 'g1d' else 0.008)
    for dx, dy, sx, sy in [(0, -h, h * 2, 0.001), (0, h, h * 2, 0.001), (-h, 0, 0.001, h * 2), (h, 0, 0.001, h * 2)]:
        bpy.ops.mesh.primitive_cube_add(size=1, location=(pos[0] + dx, pos[1] + dy, 0.00015))
        o = bpy.context.object
        o.dimensions = (sx, sy, 0.0003)
        o.data.materials.append(material)
for material in bpy.data.objects['mesh059'].data.materials:
    if material and material.node_tree:
        for node in material.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                node.inputs['Roughness'].default_value = 0.28 if a.condition != 4 else 0.48
if a.condition == 4:
    for material in materials.values():
        for node in material.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                node.inputs['Roughness'].default_value = 0.52
if a.condition == 5:
    panel = mat('background_replacement_blue_plaster', (0.12, 0.19, 0.22), 0, 0.8)
    nt = panel.node_tree
    b = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'))
    noise = nt.nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 140
    bum = nt.nodes.new('ShaderNodeBump')
    bum.inputs['Strength'].default_value = 0.12
    bum.inputs['Distance'].default_value = 0.0007
    nt.links.new(noise.outputs['Fac'], bum.inputs['Height'])
    nt.links.new(bum.outputs['Normal'], b.inputs['Normal'])
    for loc, dim in [((-0.38, -0.1, 0.65), (0.035, 3.2, 2.8)), ((1.1, 0.65, 0.65), (3.0, 0.035, 2.8))]:
        bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
        o = bpy.context.object
        o.name = 'replacement_backdrop'
        o.dimensions = dim
        o.data.materials.append(panel)
if info['robot'] == 'openarm':
    m = mat('support_pedestal', (0.06, 0.065, 0.07), 0.65, 0.35)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(info['cfg']['pos'][0], info['cfg']['pos'][1], -0.55))
    o = bpy.context.object
    o.dimensions = (0.22, 0.25, 0.4)
    o.data.materials.append(m)
lighting = [((0.7, -0.1, 1.9), 180, 1.0, (1, 0.88, 0.72)), ((1, -1.1, 1.3), 90, 1.5, (0.72, 0.84, 1))]
for loc, power, size, color in lighting:
    d = bpy.data.lights.new('physical_area', 'AREA')
    d.energy = power * (0.65 if a.condition == 1 else 1.4 if a.condition == 2 else 1)
    d.shape = 'DISK'
    d.size = size
    d.color = (1, 0.65, 0.38) if a.condition == 1 else (0.8, 0.9, 1) if a.condition == 2 else color
    o = bpy.data.objects.new(d.name, d)
    s.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector((0.55, -0.2, 0)) - o.location).to_track_quat('-Z', 'Y').to_euler()
d = bpy.data.cameras.new('overview')
cam = bpy.data.objects.new(d.name, d)
s.collection.objects.link(cam)
s.camera = cam
cam.location = (1.95, -1.1, 0.95) if info['robot'] == 'openarm' else (1.5, -1.5, 0.95) if info['robot'] == 'g1d' else (1.45, -0.65, 0.75)
target = (1.02, -0.18, 0.1) if info['robot'] == 'openarm' else (0.75, -0.3, 0.1) if info['robot'] == 'g1d' else (0.63, -0.25, 0.07)
if a.view == 'wide':
    target = (1.1, -0.1, -0.05) if info['robot'] == 'openarm' else (0.65, -0.4, -0.05) if info['robot'] == 'g1d' else (0.63, -0.25, 0.07)
cam.rotation_euler = (Vector(target) - cam.location).to_track_quat('-Z', 'Y').to_euler()
d.lens = 42 if info['robot'] != 'so101' else 38
if a.view == 'wide':
    d.lens = 24
if a.condition == 3:
    cam.location += Vector((0.08, -0.04, 0.03))
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat('-Z', 'Y').to_euler()
indices = [a.frame_index] if a.frame_index >= 0 else sorted({0, len(r['state']) // 3, len(r['state']) // 2, len(r['state']) - 1}) if a.preview else range(len(r['state']))
if any((i >= len(r['state']) for i in indices)):
    raise ValueError('Frame index outside trajectory')
selected = np.asarray(list(indices), dtype=np.int64)
for o, bid, local in objects:
    positions, quaternions = compose_visual_frames(r['body_pose'][selected, bid], list(local.translation), list(local.to_quaternion()))
    o.location = positions[0].tolist()
    o.rotation_mode = 'QUATERNION'
    o.rotation_quaternion = quaternions[0].tolist()
    if len(selected) == 1 or (np.max(np.abs(positions - positions[0])) < 1e-12 and np.max(np.abs(quaternions - quaternions[0])) < 1e-12):
        continue
    o.keyframe_insert(data_path='location', frame=0)
    o.keyframe_insert(data_path='rotation_quaternion', frame=0)
    strip = o.animation_data.action.layers[0].strips[0]
    bag = strip.channelbag(o.animation_data.action_slot)
    for curve in bag.fcurves:
        values = positions[:, curve.array_index] if curve.data_path == 'location' else quaternions[:, curve.array_index]
        curve.keyframe_points.add(len(selected) - 1)
        coordinates = np.column_stack((np.arange(len(selected), dtype=np.float32), values.astype(np.float32)))
        curve.keyframe_points.foreach_set('co', coordinates.ravel())
        for point in curve.keyframe_points:
            point.interpolation = 'LINEAR'
        curve.update()
s.frame_start = 0
s.frame_end = len(indices) - 1
s.render.filepath = str(a.out / 'frame_')
start = time.time()
bpy.ops.render.render(animation=True)
(a.out / 'render.json').write_text(json.dumps(dict(frames=len(indices), source_indices=list(indices), width=a.width, height=a.height, fps=30, engine=a.engine, samples=a.samples, elapsed_s=time.time() - start, condition=a.condition, animation_mode='bulk_quaternion_fcurves', camera=dict(position=list(cam.location), quaternion=list(cam.rotation_euler.to_quaternion()), focal_length_mm=d.lens, sensor_width_mm=d.sensor_width, convention='Blender camera: right +X, up +Y, optical axis -Z'), native_cad_color_space='URDF/MJCF RGB interpreted as sRGB', home_world_translation=[-22.35, 4.75, -0.75]), indent=2))
