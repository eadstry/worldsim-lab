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
parser.add_argument('--runtime',type=Path,required=True)
parser.add_argument('--workspace-root',type=Path,required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--camera-target',default='probe_camera',choices=['probe_camera','third_person_camera'])
parser.add_argument('--only', default='', help='Comma-separated case IDs, empty runs all cases')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
(args.output/'runner-used.py').write_bytes(Path(__file__).read_bytes())
sys.path[:0]=[str(args.runtime),str(args.workspace_root/'workspace-overlays/shared_config'),str(args.arena_root)]
source_paths = list((args.arena_root / 'isaaclab_arena/variations').glob('*.py'))
source_paths += list((args.runtime/'openarm_autodata').rglob('*.py'))
source_paths += list((args.workspace_root/'workspace-overlays/shared_config/shared_config').glob('*.py'))
source_paths += [args.arena_root / 'isaaclab_arena/environments/arena_env_builder.py', Path(__file__)]
source_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
(args.output / 'source-sha256.json').write_text(json.dumps(source_hashes, indent=2))
from isaaclab.app import AppLauncher

app = AppLauncher(headless=True, enable_cameras=True,kit_args='--enable omni.usd.schema.omni_lens_distortion').app
report = {'scope': 'Actual OpenArm left pick-place production scene in native Arena, PhysX; source robot/table/cube assets and calibrated cameras retained. Diagnostic pinhole camera added. No planner or task-success evaluation.',
          'cases': [], 'source_root': str(args.arena_root), 'status': 'running','camera_target':args.camera_target}
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

    # Load scene configs without executing AutoData-only Gym/cuRobo registrations.
    import types
    package=types.ModuleType('openarm_autodata.tasks.pick_place')
    package.__path__=[str(args.runtime/'openarm_autodata/tasks/pick_place')]
    sys.modules[package.__name__]=package
    from openarm_autodata.tasks.pick_place.configs.left_env_cfg import OpenArmLeftPickPlaceEnvCfg
    from shared_config.arena_base import OpenArmLeftEmbodiment, _scene_subset
    from shared_config.arena import CompatibleOpenArmTask, CompatibleGripperAction
    from isaaclab_physx.physics import PhysxCfg

    class ProbeTask(CompatibleOpenArmTask):
        def get_scene_cfg(self):
            return _scene_subset(self.source.scene,('ground','nightstand','table'),'ProductionProps')
        def get_events_cfg(self):
            cfg=self.source.events.copy()
            cfg.reset_cube=None  # Native Arena cube pose event is the sole pose owner.
            return cfg

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
        third_person_camera: CameraCfg | None = None
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
        eye = torch.tensor([[1.35,1.05,1.75]])
        target = torch.tensor([[.53,.10,1.10]])
        rotation = quat_from_matrix(create_rotation_matrix_from_view(eye,target))[0].tolist()
        rig.probe_camera.offset = CameraCfg.OffsetCfg(pos=tuple(eye[0].tolist()),rot=tuple(rotation),convention='opengl')
        source=OpenArmLeftPickPlaceEnvCfg()
        if args.camera_target!='probe_camera': rig.third_person_camera=source.scene.third_person_camera.copy()
        obj=Object(name='cube',prim_path=source.scene.cube.prim_path,object_type=ObjectType.RIGID,
            initial_pose=Pose(position_xyz=source.scene.cube.init_state.pos),spawner_cfg=source.scene.cube.spawn.copy())
        if kind=='pose':
            obj.set_initial_pose(PoseRange(position_xyz_min=(.49,.06,1.081),position_xyz_max=(.57,.18,1.081),rpy_min=(0.,0.,0.),rpy_max=(0.,0.,0.)))
        dome=DomeLight(instance_name='dome_light',prim_path='/World/DomeLight',spawner_cfg=source.scene.dome_light.spawn.copy())
        direct=DirectionalLight()
        assets=[obj,dome]
        if kind=='direction':
            dome.set_intensity(300.)
            direct.set_intensity(1800.)
            assets.append(direct)
        variation = None
        if kind in ('intensity','color','temperature','direction'):
            variation = (direct if kind=='direction' else dome).get_variation({'temperature':'color_temperature'}.get(kind,kind))
        elif kind == 'hdr':
            variation = dome.get_variation('hdr_image')
            direct.set_intensity(0.0)
            dome.set_intensity(1000.0)
        elif kind in ('mass','disappear'):
            variation = obj.get_variation(kind)
        elif kind == 'extrinsics':
            variation = CameraExtrinsicsVariation(args.camera_target)
            obj.add_variation(variation)
        elif kind == 'intrinsics':
            variation = CameraIntrinsicsVariation(args.camera_target, camera_rig=rig)
            obj.add_variation(variation)
        if variation is not None:
            configure_variation(variation, value, kind)

        embodiment=OpenArmLeftEmbodiment(source)
        embodiment.action_config.left_gripper_action.class_type=CompatibleGripperAction
        if args.camera_target!='probe_camera': embodiment.scene_config.third_person_camera=rig.get_cfg().third_person_camera
        def callback(cfg):
            device=cfg.sim.device
            cfg.sim=source.sim.copy()
            if cfg.sim.physics is None: cfg.sim.physics=PhysxCfg()
            cfg.sim.device=device
            cfg.decimation=source.decimation
            cfg.scene.probe_camera = rig.get_cfg().probe_camera
            cfg.wait_for_textures = True
            return cfg
        description = IsaacLabArenaEnvironment(name=f'openarm_probe_{kind}', scene=Scene(assets=assets),
            embodiment=embodiment,task=ProbeTask(source),env_cfg_callback=callback)
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
        cam = base.scene[args.camera_target]
        cam.update(dt=0.0, force_recompute=True)
        rgb = tensor(cam.data.output['rgb'])[0,...,:3].cpu().numpy().astype(np.uint8)
        Image.fromarray(rgb).save(folder/filename)
        obj = base.scene['cube']
        original=base.scene['third_person_camera']
        original.update(dt=0.,force_recompute=True)
        original_rgb=tensor(original.data.output['rgb'])[0,...,:3].cpu().numpy().astype(np.uint8)
        Image.fromarray(original_rgb).save(folder/('original-'+filename))
        sensor = cam._sensor_prims[0]
        return {'file':filename,'original_camera_file':'original-'+filename, 'cube_pose':tensor(obj.data.root_pose_w)[0].cpu().numpy().tolist(),
                'mass_kg':float(tensor(obj.data.body_mass)[0,0]),
                'camera_position_m':tensor(cam.data.pos_w)[0].cpu().numpy().tolist(),
                'opencv_fx_fy': [sensor.GetPrim().GetAttribute('omni:lensdistortion:opencvPinhole:'+k).Get() for k in ('fx','fy')],
                'camera_apertures': [float(sensor.GetHorizontalApertureAttr().Get()),float(sensor.GetVerticalApertureAttr().Get())],
                'mean_rgb':rgb.mean(axis=(0,1)).tolist()}, rgb

    specifications = [
        ('intensity', '灯光强度', [250., 3000.], 'build-time', '原场景穹顶光，强度 250 / 3000'),
        ('color', '灯光颜色', [[1.,.3,.15],[.2,.45,1.]], 'build-time', '暖红 / 冷蓝 RGB'),
        ('temperature', '灯光色温', [2800.,9000.], 'build-time', '2800 K / 9000 K'),
        ('direction', '光照方向', [[0.,.15],[1.57,1.2]], 'build-time', '原场景追加方向光；方位角/偏离天顶角 [rad]'),
        ('hdr', 'HDR 环境', ['probe_studio','probe_beach'], 'build-time', '本机真实 studio / beach HDR；未联网下载'),
        ('extrinsics', '相机外参平移', [[-.03,0.,0.],[.03,0.,0.]], 'reset', 'ROS 光学 X -30 / +30 mm；为便于观察扩展测试幅度，库默认 ±5 mm'),
        ('intrinsics', '相机内参', [[-.1,-.1],[.1,.1]], 'reset', 'fx/fy -10% / +10%，使用库默认范围端点'),
        ('mass', '物体质量', [.04,.12], 'reset', '原方块 0.04 / 0.12 kg；同一水平外力 1 N 持续 0.2 s；保留桌面接触与重力'),
        ('disappear', '物体消失', [0.,1.], 'reset', '消失概率 0 / 1；检查返回概率 0 后物体恢复'),
        ('pose', '物体位姿', [101,102], 'reset', '原任务 XY ±40/60 mm、yaw 固定，两个 seed 实际采样'),
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
                step(base, 24)
                initial = tensor(base.scene['cube'].data.root_pos_w)[0].clone()
                if kind == 'mass':
                    forces = torch.tensor([[[0.,1.,0.]]],device=base.device)
                    torques = torch.zeros_like(forces)
                    base.scene['cube'].permanent_wrench_composer.add_forces_and_torques(forces,torques,is_global=True)
                    step(base,24)
                    base.scene['cube'].permanent_wrench_composer.add_forces_and_torques(-forces,torques,is_global=True)
                    dx = float(tensor(base.scene['cube'].data.root_pos_w)[0,1]-initial[1])
                    displacements.append(dx)
                sample,image = capture(base,folder,f'{index}.png')
                sample['parameter']=value
                if kind in ('intensity','color','temperature'):
                    light = UsdLux.LightAPI(base.sim.stage.GetPrimAtPath('/World/DomeLight'))
                    sample['live_light']={'intensity':light.GetIntensityAttr().Get(),
                        'color':list(light.GetColorAttr().Get()),'color_temperature':light.GetColorTemperatureAttr().Get(),
                        'temperature_enabled':light.GetEnableColorTemperatureAttr().Get()}
                if kind=='hdr':
                    light=UsdLux.DomeLight(base.sim.stage.GetPrimAtPath('/World/DomeLight'))
                    sample['hdr_texture']=str(light.GetTextureFileAttr().Get().path)
                if kind=='direction':
                    prim=base.sim.stage.GetPrimAtPath('/World/DirectionalLight')
                    sample['directional_orientation']=list(UsdGeom.Xformable(prim).GetLocalTransformation().ExtractRotationQuat().GetImaginary())+[float(UsdGeom.Xformable(prim).GetLocalTransformation().ExtractRotationQuat().GetReal())]
                if args.camera_target!='probe_camera':
                    # Exercise the same observation refresh used by the original task.
                    base.observation_manager.compute()
                    refreshed, refreshed_rgb=capture(base,folder,f'after-observation-{index}.png')
                    sample['before_observation_position_m']=sample['camera_position_m']
                    sample['after_observation_position_m']=refreshed['camera_position_m']
                    sample['after_observation_file']=refreshed['file']
                    sample['after_observation_rgb_mad']=float(np.abs(image.astype(float)-refreshed_rgb.astype(float)).mean())
                record['samples'].append(sample); images.append(image)
                if kind=='mass':record['displacement_y_m']=displacements.copy()
            mad = float(np.abs(images[0].astype(float)-images[1].astype(float)).mean())
            record['pixel_mean_absolute_difference']=mad
            checks={'finite_state':all(np.isfinite(s['cube_pose']).all() for s in record['samples']),
                    'nonblack_frames':all(float(im.mean())>1 for im in images), 'visible_difference':mad>.5}
            if kind=='mass':
                checks['masses_applied']=all(abs(s['mass_kg']-v)<1e-5 for s,v in zip(record['samples'],values))
                checks['mass_contact_response']=abs(displacements[0]-displacements[1])>.002
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
                checks['returns_after_reset']=abs(float(tensor(base.scene['cube'].data.root_pos_w)[0,0])-.53)<.01
            elif kind=='pose':
                checks['within_range']=all(.48999<=s['cube_pose'][0]<=.57001 and .05999<=s['cube_pose'][1]<=.18001 for s in record['samples'])
            elif kind=='intensity':
                checks['live_parameter_applied']=all(abs(s['live_light']['intensity']-v)<1e-5 for s,v in zip(record['samples'],values))
            elif kind=='color':
                checks['live_parameter_applied']=all(np.allclose(s['live_light']['color'],v,atol=1e-5) for s,v in zip(record['samples'],values))
            elif kind=='temperature':
                checks['live_parameter_applied']=all(s['live_light']['temperature_enabled'] and abs(s['live_light']['color_temperature']-v)<1e-3 for s,v in zip(record['samples'],values))
            if kind=='hdr':
                checks['hdr_texture_applied']=all(s['hdr_texture']==LOCAL_HDRS[v] for s,v in zip(record['samples'],values))
            if kind=='direction':
                checks['direction_changed']=not np.allclose(record['samples'][0]['directional_orientation'],record['samples'][1]['directional_orientation'])
            if args.camera_target!='probe_camera' and kind=='extrinsics':
                refreshed_distance=float(np.linalg.norm(np.subtract(record['samples'][1]['after_observation_position_m'],record['samples'][0]['after_observation_position_m'])))
                record['after_observation_camera_shift_m']=refreshed_distance
                checks['shift_survives_observation']=abs(refreshed_distance-.06)<1e-5
            if args.camera_target!='probe_camera' and kind=='intrinsics':
                record['opencv_focal_lengths_changed']=not np.allclose(record['samples'][0]['opencv_fx_fy'],record['samples'][1]['opencv_fx_fy'])
                checks['opencv_focal_lengths_changed']=record['opencv_focal_lengths_changed']
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
except Exception:
    report['status']='failed'
    report['error']=traceback.format_exc()
    (args.output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(report['error'],flush=True)
finally:
    if env is not None:env.close()
    app.close()
