# SPDX-License-Identifier: Apache-2.0
"""Add a full-scene diagnostic camera to the official G1 Mimic generation workflow."""

def register():
    from isaaclab_arena.environments.isaaclab_interop import environment_registration_callback
    remaining = environment_registration_callback()
    # The stock G1 Mimic class predates Arena's progress-tracker property.
    from isaaclab_arena.embodiments.g1.g1 import G1MimicEnv
    if not hasattr(G1MimicEnv, 'progress_tracker'):
        G1MimicEnv.progress_tracker = property(lambda env: getattr(env, '_progress_tracker', None))
    from isaaclab_arena.environments.arena_world import ArenaWorld
    from isaaclab_arena.tasks.predicates.object_settling import ObjectInitialRestPoseRecorder
    def arena_world(env):
        if not hasattr(env, '_arena_world'):
            env._arena_world = ArenaWorld(env.scene)
        return env._arena_world
    def rest_recorder(env):
        if not hasattr(env, '_object_initial_rest_pose_recorder'):
            env._object_initial_rest_pose_recorder = ObjectInitialRestPoseRecorder(env.num_envs, env.device)
        return env._object_initial_rest_pose_recorder
    if not hasattr(G1MimicEnv, 'arena_world'):
        G1MimicEnv.arena_world = property(arena_world)
    if not hasattr(G1MimicEnv, 'object_initial_rest_pose_recorder'):
        G1MimicEnv.object_initial_rest_pose_recorder = property(rest_recorder)
    import isaaclab_mimic.datagen.generation as generation
    original = generation.setup_env_config
    # Observe the existing placement success criterion after a 2-second settling hold.
    import inspect
    import textwrap
    from isaaclab_mimic.datagen.data_generator import DataGenerator
    source = textwrap.dedent(inspect.getsource(DataGenerator.generate))
    export_anchor = '    # Set success to the recorded episode data and export to file'
    assert source.count(export_anchor) == 1, 'Review changed upstream generator export'
    source = source.replace(export_anchor, """    for _ in range(100):
        exec_success = await multi_waypoint.execute(
            env=self.env, success_term=success_term, env_id=env_id,
            env_action_queue=env_action_queue,
        )
        generated_success = generated_success or exec_success

""" + export_anchor, 1)
    scope = {}
    exec(compile(source, '<g1-final-settling-hold>', 'exec'), DataGenerator.generate.__globals__, scope)
    DataGenerator.generate = scope['generate']

    def setup(**kwargs):
        import torch
        import isaaclab.sim as sim
        from isaaclab.sensors import CameraCfg
        from isaaclab.managers import RecorderTerm, RecorderTermCfg
        from isaaclab.utils.math import create_rotation_matrix_from_view, quat_from_matrix
        cfg, success = original(**kwargs)
        import faulthandler
        faulthandler.cancel_dump_traceback_later()
        from isaaclab.managers import DatasetExportMode
        import os
        cfg.seed = cfg.datagen_config.seed = int(os.environ.get('G1_SEED', '1'))
        cfg.datagen_config.generation_guarantee = False
        cfg.datagen_config.generation_keep_failed = True
        cfg.recorders.dataset_export_mode = DatasetExportMode.EXPORT_ALL
        # Mimic removes terminations and calls success.func directly. Arena's
        # stateful term still needs manager initialization and per-episode resets.
        from copy import deepcopy
        from isaaclab_arena.progress_tracking.task_success import TaskSuccessTerm
        assert success.func is TaskSuccessTerm, 'Review changed upstream success API'
        class TrackingOnlySuccess(TaskSuccessTerm):
            def __call__(self, env, success_objectives, subtasks_are_sequential=False,
                         desired_subtask_success_state=None):
                complete = super().__call__(env, success_objectives, subtasks_are_sequential,
                                            desired_subtask_success_state)
                return torch.zeros_like(complete)
        tracking = deepcopy(success)
        tracking.func = TrackingOnlySuccess
        cfg.terminations = {'progress_tracking': tracking}
        def read_success(env, **params):
            return env.progress_tracker.is_complete()
        success.func = read_success
        eye = (0.0, -3.6, 1.2)
        target = (0.0, -0.6, 0.1)
        rot = quat_from_matrix(create_rotation_matrix_from_view(torch.tensor([eye]), torch.tensor([target])))[0]
        cfg.scene.overview_camera = CameraCfg(
            prim_path='{ENV_REGEX_NS}/OverviewCamera', width=640, height=360,
            update_period=0.0, data_types=['rgb'],
            spawn=sim.PinholeCameraCfg(focal_length=18, horizontal_aperture=36, vertical_aperture=20.25,
                                      clipping_range=(0.05, 100)),
            offset=CameraCfg.OffsetCfg(pos=eye, rot=tuple(rot.tolist()), convention='opengl'),
        )
        class OverviewRecorder(RecorderTerm):
            def record_pre_step(self):
                if generation.num_failures >= 3:
                    raise RuntimeError('Stopped after three failed G1 generation attempts')
                rgb = self._env.scene['overview_camera'].data.output['rgb'][..., :3].clone()
                self._preview_step = getattr(self, '_preview_step', 0) + 1
                if self._preview_step in (1, 100, 400, 800):
                    from pathlib import Path
                    from PIL import Image
                    folder = Path(kwargs['output_dir'])
                    folder.mkdir(parents=True, exist_ok=True)
                    Image.fromarray(rgb[0].cpu().numpy()).save(folder / f'overview-preview-{self._preview_step}.png')
                return 'overview_rgb', rgb
        cfg.recorders.overview_rgb = RecorderTermCfg(class_type=OverviewRecorder)
        cfg.datagen_config.max_num_failures = 3
        cfg.wait_for_textures = True
        print(f'G1_CAPTURE: attempts={cfg.datagen_config.generation_num_trials}, seed={cfg.seed}; success flags retained, overview 640x360', flush=True)
        return cfg, success
    generation.setup_env_config = setup
    return remaining
