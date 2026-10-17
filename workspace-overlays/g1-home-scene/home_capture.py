# SPDX-License-Identifier: Apache-2.0
"""Reuse G1 generation and official success predicates in a prepared home scene."""
import os
from pathlib import Path


def register():
    from isaaclab_arena.assets.background_library import GalileoLocomanipBackground
    from isaaclab_arena.utils.pose import Pose
    layer = Path(os.environ['G1_HOME_USD']).resolve()
    assert layer.is_file(), layer
    GalileoLocomanipBackground.usd_path = str(layer)
    GalileoLocomanipBackground.initial_pose = Pose.identity()
    import g1_capture
    remaining = g1_capture.register()
    import isaaclab_mimic.datagen.generation as generation
    original = generation.setup_env_config

    def setup(**kwargs):
        import torch
        from isaaclab.utils.math import create_rotation_matrix_from_view, quat_from_matrix
        cfg, success = original(**kwargs)
        eye, target = (-1.25, -1.4, 1.25), (0.0, -0.65, -0.05)
        rot = quat_from_matrix(create_rotation_matrix_from_view(torch.tensor([eye]), torch.tensor([target])))[0]
        cfg.scene.overview_camera.offset.pos = eye
        cfg.scene.overview_camera.offset.rot = tuple(rot.tolist())
        cfg.scene.overview_camera.spawn.focal_length = 14.0
        cfg.scene.galileo_locomanip.spawn.func = __import__('isaaclab.sim', fromlist=['spawn_from_usd']).spawn_from_usd
        from isaaclab.sensors import CameraCfg
        import isaaclab.sim as sim
        from isaaclab.managers import RecorderTerm, RecorderTermCfg
        house_eye, house_target = (0.5, -3.4, 10.5), (0.5, -3.0, -0.795)
        house_rot = quat_from_matrix(create_rotation_matrix_from_view(
            torch.tensor([house_eye]), torch.tensor([house_target])))[0]
        cfg.scene.house_camera = CameraCfg(
            prim_path='{ENV_REGEX_NS}/HouseCamera', width=640, height=640,
            update_period=1.0, data_types=['rgb'],
            spawn=sim.PinholeCameraCfg(focal_length=28, horizontal_aperture=36,
                                      vertical_aperture=36, clipping_range=(0.05, 100)),
            offset=CameraCfg.OffsetCfg(pos=house_eye, rot=tuple(house_rot.tolist()), convention='opengl'),
        )
        class HouseSnapshots(RecorderTerm):
            def record_pre_step(self):
                self._step = getattr(self, '_step', 0) + 1
                if self._step in (100, 400, 800):
                    from PIL import Image
                    rgb = self._env.scene['house_camera'].data.output['rgb'][0, ..., :3]
                    folder = Path(kwargs['output_dir'])
                    folder.mkdir(parents=True, exist_ok=True)
                    Image.fromarray(rgb.cpu().numpy()).save(folder / f'house-{self._step}.png')
                return None, None
        cfg.recorders.house_snapshots = RecorderTermCfg(class_type=HouseSnapshots)
        print(f'G1_HOME: layer={layer}; static household collision; original task predicates', flush=True)
        return cfg, success
    generation.setup_env_config = setup
    return remaining
