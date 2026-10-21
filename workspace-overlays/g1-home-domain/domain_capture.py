# SPDX-License-Identifier: Apache-2.0
"""Apply a planned domain sample and read actual simulator values back."""
import hashlib
import json
import math
import os
from pathlib import Path


def register():
    path = Path(os.environ['G1_DR_PLAN']).resolve()
    plan = json.loads(path.read_text())
    assert plan['schema_version'] == 1
    for key in ('scene', 'base_layer', 'hdr'):
        assert hashlib.sha256(Path(plan[key]).read_bytes()).hexdigest() == plan[key + '_sha256'], key
    assert int(os.environ.get('G1_SEED', '1')) == plan['generation_seed']
    os.environ['G1_HOME_USD'] = plan['scene']
    import home_capture
    remaining = home_capture.register()
    import isaaclab_mimic.datagen.generation as generation
    original = generation.setup_env_config

    def setup(**kwargs):
        import torch
        from isaaclab.managers import RecorderTerm, RecorderTermCfg
        from isaaclab.utils.math import quat_from_euler_xyz, quat_mul
        cfg, success = original(**kwargs)
        sampled = plan['sampled']
        camera = cfg.scene.robot_head_cam
        if 'camera' in sampled:
            value = sampled['camera']
            camera.offset.pos = tuple(a + b for a, b in zip(camera.offset.pos, value['local_translation_m']))
            angles = [torch.tensor(math.radians(v)) for v in value['local_rpy_deg']]
            delta = quat_from_euler_xyz(*angles)
            # Isaac Lab math uses XYZW quaternions in this configured runtime.
            camera.offset.rot = tuple(quat_mul(torch.tensor(camera.offset.rot), delta).tolist())
            camera.spawn.focal_length *= value['focal_scale']
        if 'pose' in sampled:
            value = sampled['pose']
            pose_range = cfg.events.brown_box.params['pose_range']
            r, yaw = value['xy_half_range_m'], math.radians(value['yaw_half_range_deg'])
            pose_range['x'] = (.5785 - r, .5785 + r)
            pose_range['y'] = (.18 - r, .18 + r)
            pose_range['yaw'] = (math.pi - yaw, math.pi + yaw)
        output = Path(kwargs['output_dir'])
        resolved = dict(plan=plan, camera_cfg=dict(pos=list(camera.offset.pos), rot=list(camera.offset.rot),
                        convention=camera.offset.convention, focal_length=camera.spawn.focal_length),
                        pose_range=cfg.events.brown_box.params['pose_range'])
        output.mkdir(parents=True, exist_ok=True)
        (output / 'dr-resolved.json').write_text(json.dumps(resolved, indent=2))

        class DomainReadback(RecorderTerm):
            def record_pre_step(self):
                from pxr import UsdLux
                if not getattr(self, '_read_back', False):
                    env = self._env
                    prefix = '/World/envs/env_0/galileo_locomanip'
                    dome = UsdLux.DomeLight(env.sim.stage.GetPrimAtPath(prefix + '/DiagnosticDome'))
                    key = UsdLux.RectLight(env.sim.stage.GetPrimAtPath(prefix + '/DiagnosticKey'))
                    actual = dict(dome_intensity=dome.GetIntensityAttr().Get(),
                                  key_intensity=key.GetIntensityAttr().Get(),
                                  key_temperature_k=key.GetColorTemperatureAttr().Get(),
                                  hdr=str(dome.GetTextureFileAttr().Get()),
                                  camera_intrinsics=env.scene['robot_head_cam'].data.intrinsic_matrices[0].tolist(),
                                  camera_pos_w=env.scene['robot_head_cam'].data.pos_w[0].tolist())
                    if 'lighting' in sampled:
                        assert math.isclose(actual['dome_intensity'], sampled['lighting']['dome_intensity'], rel_tol=1e-5)
                    (output / 'dr-readback.json').write_text(json.dumps(actual, indent=2))
                    self._read_back = True
                return 'dr_success_observed', self._env.progress_tracker.is_complete().clone()
        cfg.recorders.domain_readback = RecorderTermCfg(class_type=DomainReadback)
        print('G1_DR: ' + json.dumps(resolved), flush=True)
        return cfg, success
    generation.setup_env_config = setup
    return remaining
