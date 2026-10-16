# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Exercise Arena variations through ArenaEnvBuilder and save real RTX images."""
import argparse
import ast
import hashlib
import json
import math
import os
import sys
import traceback
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--arena-root', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--only', default='', help='Comma-separated case IDs, empty runs all cases')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
sys.path.insert(0, str(args.arena_root))
source_paths = list((args.arena_root / 'isaaclab_arena/variations').glob('*.py'))
source_paths += [args.arena_root / 'isaaclab_arena/environments/arena_env_builder.py', Path(__file__)]
source_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
(args.output / 'source-sha256.json').write_text(json.dumps(source_hashes, indent=2))
from isaaclab.app import AppLauncher

app = AppLauncher(headless=True, enable_cameras=True).app
report = {'scope': 'Real Arena variations on a minimal primitive scene, PhysX backend. No robot policy, planner or task-success evaluation.',
          'cases': [], 'source_root': str(args.arena_root), 'status': 'running'}
env = None
try:
    import numpy as np
    import torch
    import warp as wp
    from PIL import Image
    from pxr import UsdGeom, UsdLux
    import isaaclab.sim as sim_utils
    from isaaclab.sensors import CameraCfg
    from isaaclab.utils.configclass import configclass
    from isaaclab.utils.math import create_rotation_matrix_from_view, quat_from_matrix
    from isaaclab_arena.assets.hdr_image import HDRImage
    from isaaclab_arena.assets.object import Object
    from isaaclab_arena.assets.object_base import ObjectType
    from isaaclab_arena.assets.object_library import DomeLight, DirectionalLight, Sphere, GroundPlane
    from isaaclab_arena.assets.registries import HDRImageRegistry
    from isaaclab_arena.environments.arena_env_builder import ArenaEnvBuilder, ArenaEnvBuilderCfg
    from isaaclab_arena.environments.isaaclab_arena_environment import IsaacLabArenaEnvironment
    from isaaclab_arena.scene.scene import Scene
    from isaaclab_arena.utils.cameras import ArenaCameraCfg
    from isaaclab_arena.utils.pose import Pose, PoseRange
    from isaaclab_arena.variations.uniform_sampler import UniformSamplerCfg
    from isaaclab_arena.variations.bernoulli_sampler import BernoulliSamplerCfg
    from isaaclab_arena.variations.camera_extrinsics_variation import CameraExtrinsicsVariation
    from isaaclab_arena.variations.camera_intrinsics_variation import CameraIntrinsicsVariation

    LOCAL_HDRS = {
        'probe_studio': '/opt/isaac-sim6.0/extscache/omni.kit.thumbnails.mdl-1.0.28+110.1.1/data/tests/template/SubUSDs/textures/photo_studio_01_4k.hdr',
        'probe_beach': '/opt/isaac-sim6.0/extscache/omni.usd.libs-1.0.3+6312fa25.lx64.r.cp312/bin/usd/hdx/resources/textures/StinsonBeach.hdr',
    }
    for name, texture in LOCAL_HDRS.items():
        assert Path(texture).is_file(), texture
        cls = type('LocalHDR_' + name, (HDRImage,), {
            '__init__': lambda self, n=name, p=texture: HDRImage.__init__(self, name=n, texture_file=p)})
        HDRImageRegistry().register(cls, key=name)

    def tensor(value):
        return value if isinstance(value, torch.Tensor) else wp.to_torch(value)

    @configclass
    class ProbeRig(ArenaCameraCfg):
        probe_camera: CameraCfg = CameraCfg(
            prim_path='{ENV_REGEX_NS}/ProbeCamera', update_period=0.0, height=360, width=480,
            data_types=['rgb'], spawn=sim_utils.PinholeCameraCfg(
                focal_length=24.0, horizontal_aperture=24.0, clipping_range=(.01, 2000.0)))

    def configure_variation(variation, value, kind):
        if kind == 'hdr':
            cfg = type(variation.cfg)(enabled=True, hdr_names=[value])
        elif kind == 'disappear':
            cfg = type(variation.cfg)(enabled=True, sampler_cfg=BernoulliSamplerCfg(probability=value))
        else:
            values = value if isinstance(value, list) else [value]
            cfg = type(variation.cfg)(enabled=True, sampler_cfg=UniformSamplerCfg(low=values, high=values))
        variation.apply_cfg(cfg)

    def build(kind, value):
        rig = ProbeRig()
        rig.set_use_tiled_camera(False)
        eye = torch.tensor([[.75,.75,.70]])
        target = torch.tensor([[0.,0.,.14]])
        rotation = quat_from_matrix(create_rotation_matrix_from_view(eye,target))[0].tolist()
        rig.probe_camera.offset = CameraCfg.OffsetCfg(pos=tuple(eye[0].tolist()),rot=tuple(rotation),convention='opengl')
        obj = Object(name='probe_object', object_type=ObjectType.RIGID,
                     initial_pose=Pose(position_xyz=(0., 0., .18)),
                     spawner_cfg=sim_utils.CuboidCfg(
                         size=(.16, .08, .12), visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(.75,.18,.12)),
                         collision_props=sim_utils.CollisionPropertiesCfg(),
                         rigid_props=sim_utils.RigidBodyPropertiesCfg(disable_gravity=True),
                         mass_props=sim_utils.MassPropertiesCfg(mass=.25)))
        if kind == 'pose':
            obj.set_initial_pose(PoseRange(position_xyz_min=(-.10,-.10,.18),
                position_xyz_max=(.10,.10,.18), rpy_min=(0.,0.,-.8), rpy_max=(0.,0.,.8)))
        references = []
        for name, position, color in (
            ('reference_blue', (.24,.12,.12), (.1,.3,.8)),
            ('reference_green', (-.22,-.12,.12), (.1,.65,.2))):
            spawn = Sphere.default_spawner_cfg.copy()
            spawn.radius = .06
            spawn.rigid_props.disable_gravity = True
            spawn.visual_material.diffuse_color = color
            references.append(Sphere(instance_name=name, initial_pose=Pose(position_xyz=position), spawner_cfg=spawn))
        dome_cfg = DomeLight.default_spawner_cfg.copy()
        dome_cfg.intensity = 300.0
        dome_cfg.color = (1.,1.,1.)
        dome = DomeLight(spawner_cfg=dome_cfg)
        direct_cfg = DirectionalLight.default_spawner_cfg.copy()
        direct_cfg.intensity = 1800.0
        direct = DirectionalLight(spawner_cfg=direct_cfg)
        direct.set_orientation((0., math.sin(.35), 0., math.cos(.35)))
        variation = None
        if kind in ('intensity','color','temperature','direction'):
            variation = direct.get_variation({'temperature':'color_temperature'}.get(kind,kind))
        elif kind == 'hdr':
            variation = dome.get_variation('hdr_image')
            direct.set_intensity(0.0)
            dome.set_intensity(1000.0)
        elif kind in ('mass','disappear'):
            variation = obj.get_variation(kind)
        elif kind == 'extrinsics':
            variation = CameraExtrinsicsVariation('probe_camera')
            obj.add_variation(variation)
        elif kind == 'intrinsics':
            variation = CameraIntrinsicsVariation('probe_camera', camera_rig=rig)
            obj.add_variation(variation)
        if variation is not None:
            configure_variation(variation, value, kind)

        def callback(cfg):
            cfg.scene.probe_camera = rig.get_cfg().probe_camera
            cfg.wait_for_textures = True
            if kind == 'mass':
                # Isolate force/mass response from gravity and ground contact.
                cfg.sim.gravity = (0.0, 0.0, 0.0)
            return cfg

        description = IsaacLabArenaEnvironment(
            name=f'probe_{kind}', scene=Scene(assets=[GroundPlane(),obj,*references,dome,direct]),
            env_cfg_callback=callback)
        builder = ArenaEnvBuilder(description, ArenaEnvBuilderCfg(
            num_envs=1, env_spacing=2.0, seed=101, solve_relations=False, device='cuda:0'))
        wrapped = builder.make_registered()
        return wrapped, variation

    def step(base, count):
        for _ in range(count):
            base.scene.write_data_to_sim()
            base.sim.step()
            base.scene.update(base.physics_dt)

    def capture(base, folder, filename):
        for _ in range(5): base.sim.render()
        cam = base.scene['probe_camera']
        cam.update(dt=0.0, force_recompute=True)
        rgb = tensor(cam.data.output['rgb'])[0,...,:3].cpu().numpy().astype(np.uint8)
        Image.fromarray(rgb).save(folder/filename)
        obj = base.scene['probe_object']
        sensor = cam._sensor_prims[0]
        return {'file':filename, 'cube_pose':tensor(obj.data.root_pose_w)[0].cpu().numpy().tolist(),
                'mass_kg':float(tensor(obj.data.body_mass)[0,0]),
                'camera_position_m':tensor(cam.data.pos_w)[0].cpu().numpy().tolist(),
                'camera_apertures': [float(sensor.GetHorizontalApertureAttr().Get()),float(sensor.GetVerticalApertureAttr().Get())],
                'mean_rgb':rgb.mean(axis=(0,1)).tolist()}, rgb

    specifications = [
        ('intensity', '灯光强度', [250., 3000.], 'build-time', '同一方向光，强度 250 / 3000'),
        ('color', '灯光颜色', [[1.,.3,.15],[.2,.45,1.]], 'build-time', '暖红 / 冷蓝 RGB'),
        ('temperature', '灯光色温', [2800.,9000.], 'build-time', '2800 K / 9000 K'),
        ('direction', '光照方向', [[0.,.15],[1.57,1.2]], 'build-time', '方位角/偏离天顶角 [rad]'),
        ('hdr', 'HDR 环境', ['probe_studio','probe_beach'], 'build-time', '本机真实 studio / beach HDR；未联网下载'),
        ('extrinsics', '相机外参平移', [[-.03,0.,0.],[.03,0.,0.]], 'reset', 'ROS 光学 X -30 / +30 mm；为便于观察扩展测试幅度，库默认 ±5 mm'),
        ('intrinsics', '相机内参', [[-.1,-.1],[.1,.1]], 'reset', 'fx/fy -10% / +10%，使用库默认范围端点'),
        ('mass', '物体质量', [.05,.25], 'reset', '0.05 / 0.25 kg；同一外力 0.05 N 持续 0.4 s，无重力'),
        ('disappear', '物体消失', [0.,1.], 'reset', '消失概率 0 / 1；检查返回概率 0 后物体恢复'),
        ('pose', '物体位姿', [101,102], 'reset', 'XY ±100 mm、yaw ±0.8 rad，两个 seed 实际采样'),
    ]
    for kind, label, values, phase, note in specifications:
        if args.only and kind not in args.only.split(','):
            continue
        record = {'id':kind,'label':label,'phase':phase,'note':note,'parameters':values,'status':'running','samples':[]}
        report['cases'].append(record)
        folder = args.output/kind
        folder.mkdir()
        images = []
        displacements = []
        try:
            for index, value in enumerate(values):
                if env is None or phase == 'build-time':
                    if env is not None:
                        env.close(); env=None
                    env, variation = build(kind, value)
                elif variation is not None:
                    configure_variation(variation, value, kind)
                    name, _ = variation.build_event_cfg()
                    term = env.unwrapped.event_manager.get_term_cfg(name)
                    term.params['sampler'] = variation.sampler
                    env.unwrapped.event_manager.set_term_cfg(name,term)
                base = env.unwrapped
                env.reset(seed=value if kind=='pose' else 101)
                step(base, 2)
                initial = tensor(base.scene['probe_object'].data.root_pos_w)[0].clone()
                if kind == 'mass':
                    forces = torch.tensor([[[.05,0.,0.]]],device=base.device)
                    torques = torch.zeros_like(forces)
                    base.scene['probe_object'].permanent_wrench_composer.add_forces_and_torques(forces,torques,is_global=True)
                    step(base,48)
                    base.scene['probe_object'].permanent_wrench_composer.add_forces_and_torques(-forces,torques,is_global=True)
                    dx = float(tensor(base.scene['probe_object'].data.root_pos_w)[0,0]-initial[0])
                    displacements.append(dx)
                sample,image = capture(base,folder,f'{index}.png')
                sample['parameter']=value
                if kind in ('intensity','color','temperature'):
                    light = UsdLux.LightAPI(base.sim.stage.GetPrimAtPath('/World/DirectionalLight'))
                    sample['live_light']={'intensity':light.GetIntensityAttr().Get(),
                        'color':list(light.GetColorAttr().Get()),'color_temperature':light.GetColorTemperatureAttr().Get(),
                        'temperature_enabled':light.GetEnableColorTemperatureAttr().Get()}
                record['samples'].append(sample); images.append(image)
                if kind=='mass':record['displacement_x_m']=displacements.copy()
            mad = float(np.abs(images[0].astype(float)-images[1].astype(float)).mean())
            record['pixel_mean_absolute_difference']=mad
            checks={'finite_state':all(np.isfinite(s['cube_pose']).all() for s in record['samples']),
                    'nonblack_frames':all(float(im.mean())>1 for im in images), 'visible_difference':mad>.5}
            if kind=='mass':
                checks['masses_applied']=all(abs(s['mass_kg']-v)<1e-5 for s,v in zip(record['samples'],values))
                checks['inverse_mass_response']=abs(displacements[0]/displacements[1]-5.)<.3
            elif kind=='extrinsics':
                distance=float(np.linalg.norm(np.subtract(record['samples'][1]['camera_position_m'],record['samples'][0]['camera_position_m'])))
                record['camera_shift_m']=distance
                checks['camera_shift_applied']=abs(distance-.06)<1e-5
            elif kind=='intrinsics':
                apertures=[s['camera_apertures'] for s in record['samples']]
                checks['aperture_ratio']=np.allclose(np.array(apertures[0])/apertures[1],1.1/.9,atol=1e-5)
            elif kind=='disappear':
                checks['parked_away']=record['samples'][1]['cube_pose'][0]>900.
                configure_variation(variation,0.,kind)
                name,_=variation.build_event_cfg();term=base.event_manager.get_term_cfg(name)
                term.params['sampler']=variation.sampler;base.event_manager.set_term_cfg(name,term)
                env.reset();step(base,2)
                checks['returns_after_reset']=abs(float(tensor(base.scene['probe_object'].data.root_pos_w)[0,0]))<.01
            elif kind=='pose':
                checks['within_range']=all(abs(s['cube_pose'][0])<=.10001 and abs(s['cube_pose'][1])<=.10001 for s in record['samples'])
            elif kind=='intensity':
                checks['live_parameter_applied']=all(abs(s['live_light']['intensity']-v)<1e-5 for s,v in zip(record['samples'],values))
            elif kind=='color':
                checks['live_parameter_applied']=all(np.allclose(s['live_light']['color'],v,atol=1e-5) for s,v in zip(record['samples'],values))
            elif kind=='temperature':
                checks['live_parameter_applied']=all(s['live_light']['temperature_enabled'] and abs(s['live_light']['color_temperature']-v)<1e-3 for s,v in zip(record['samples'],values))
            record['checks']={k:bool(v) for k,v in checks.items()}
            record['status']='passed' if all(checks.values()) else 'failed'
        except Exception:
            record['status']='failed';record['error']=traceback.format_exc()
            (folder/'error.txt').write_text(record['error'])
        finally:
            if env is not None:
                env.close();env=None
            (args.output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
            print('CASE_RESULT '+json.dumps(record,ensure_ascii=False),flush=True)
    concrete=[]
    for p in (args.arena_root/'isaaclab_arena/variations').glob('*_variation.py'):
        for node in ast.parse(p.read_text()).body:
            if isinstance(node,ast.ClassDef) and any(isinstance(b,ast.Name) and b.id in ('BuildTimeVariationBase','RunTimeVariationBase') for b in node.bases):
                concrete.append({'class':node.name,'source':str(p),'line':node.lineno})
    report['concrete_variations']=concrete
    report['source_unchanged']=all(hashlib.sha256(p.read_bytes()).hexdigest()==source_hashes[str(p)] for p in source_paths)
    report['status']='passed' if all(c['status']=='passed' for c in report['cases']) and report['source_unchanged'] else 'failed'
    (args.output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print('FINAL_STATUS '+report['status'],flush=True)
finally:
    if env is not None:env.close()
    app.close()
