# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
import asyncio
from pathlib import Path
import unittest
from types import SimpleNamespace
from launch import bounded_source, generator_guard


class BudgetTests(unittest.TestCase):
    def test_finished_environments_keep_batch_queue_alive_without_new_attempts(self):
        # Exercise generated producer code: a fast environment exhausts its quota
        # while the other still needs batched simulation actions.
        source = '''async def producer(env, env_id, env_reset_queue, env_action_queue, data_generator, success_term, pause_subtask, stats):
    while True:
        try:
            result = await data_generator.generate(env_id, env_action_queue)
        except Exception:
            raise
        stats['num_attempts'] += 1


def build_datastream():
    generation_policy_params = task_descriptor.get_generation_policy()
    env = gym.make(env_name, cfg=env_cfg).unwrapped
'''
        import numpy as np
        class Torch:
            @staticmethod
            def zeros(shape, **kw):
                return np.zeros(shape)
        namespace = {'torch': Torch, 'asyncio': asyncio}
        exec(bounded_source(source, 4, 2), namespace)
        async def run():
            queue = asyncio.Queue()
            calls = [0, 0]
            class Generator:
                async def generate(self, env_id, queue):
                    calls[env_id] += 1
                    for _ in range(1 if env_id == 0 else 3):
                        await queue.put((env_id, np.zeros(7)))
                        await queue.join()
            env = SimpleNamespace(action_space=SimpleNamespace(shape=(2, 7)), device='cpu',
                action_manager=SimpleNamespace(action=np.zeros((2, 7))))
            stats = {'num_attempts': 0}
            tasks = [asyncio.create_task(namespace['producer'](env, i, None, queue, Generator(), None, False, stats)) for i in range(2)]
            for _ in range(30):
                for _ in range(30):
                    await asyncio.sleep(0)
                    if queue.qsize() == 2:
                        break
                self.assertEqual(queue.qsize(), 2)
                batch = [queue.get_nowait() for _ in range(2)]
                self.assertEqual(sorted(i for i, _ in batch), [0, 1])
                queue.task_done()
                queue.task_done()
                await asyncio.sleep(0)
                if stats['num_attempts'] == 4:
                    break
            self.assertEqual(stats['num_attempts'], 4)
            self.assertEqual(calls, [2, 2])
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        asyncio.run(run())

    def test_invalid_quota(self):
        for attempts, envs in [(0, 1), (2, 4), (5, 4)]:
            with self.assertRaises(ValueError):
                bounded_source('', attempts, envs)

    def test_changed_boundary_fails_closed(self):
        with self.assertRaises(ValueError):
            bounded_source('upstream changed', 4, 4)
        with self.assertRaises(ValueError):
            generator_guard('upstream changed')

    def test_terminal_checked_even_if_accumulated_success_false(self):
        transformed = generator_guard('    env.recorder_manager.set_success_to_episodes(\n')
        self.assertLess(transformed.index('terminal_pass ='), transformed.index('buffers.success ='))


if __name__ == '__main__':
    unittest.main()

class ValidationTests(unittest.TestCase):
    def setUp(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'openarm-throughput-benchmark'))

    def fixture(self, path, label=True, nan=False, moving=False):
        import h5py
        import numpy as np
        with h5py.File(path, 'w') as file:
            episode = file.create_group('data/demo_0')
            episode.attrs['success'] = label
            actions = np.zeros((2, 7))
            if nan:
                actions[1, 0] = np.nan
            episode.create_dataset('actions', data=actions)
            for camera in ('left_hand_rgb', 'right_hand_rgb', 'third_person_rgb'):
                episode.create_dataset('obs/'+camera, shape=(2,480,640,3), dtype='uint8', compression='gzip', fillvalue=0)
            for key, value in [('cube/root_pose',[.35,.20,.5395,0,0,0,1]),('table/root_pose',[0,0,0,0,0,0,1]),('cube/root_velocity',[1 if moving else 0,0,0,0,0,0])]:
                episode.create_dataset('states/rigid_object/'+key,data=np.array([value,value]))
            joints=np.zeros((2,18));joints[:,14]=.4
            episode.create_dataset('states/articulation/robot/joint_position',data=joints)

    def test_good_record_and_exact_count(self):
        import tempfile
        from run import validate
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'dataset.hdf5'
            self.fixture(output)
            result=validate(output,1)
            self.assertEqual(len(result['episodes']),1)
            with self.assertRaises(ValueError):
                validate(output,2)

    def test_nonfinite_and_false_success_rejected(self):
        import tempfile
        from run import validate
        for kwargs in ({'nan':True},{'moving':True}):
            with tempfile.TemporaryDirectory() as tmp:
                output=Path(tmp)/'dataset.hdf5'
                self.fixture(output,**kwargs)
                with self.assertRaises(ValueError):
                    validate(output,1)

    def test_failed_episode_kept_but_not_counted_as_success(self):
        import tempfile
        from run import validate
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'dataset.hdf5'
            self.fixture(output.with_name('dataset_failed.hdf5'),label=False,moving=True)
            result=validate(output,0)
            self.assertFalse(result['episodes'][0]['terminal_pass'])

class VideoTests(ValidationTests):
    def test_nested_video_destination_and_encoded_dimensions(self):
        import tempfile
        import imageio_ffmpeg
        from run import validate, videos
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            output = base/'dataset.hdf5'
            self.fixture(output)
            destination = base/'videos'/'env1-workers0'
            already_saved = set()
            result = videos(output, validate(output, 1), destination, already_saved)
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(already_saved, {'success'})
            self.assertEqual(videos(output, validate(output, 1), destination, already_saved)['files'], [])
            reader = imageio_ffmpeg.read_frames(str(destination/'success.mp4'))
            metadata = next(reader)
            self.assertEqual(metadata['size'], (320,240))
            self.assertEqual(metadata['fps'], 15)
            reader.close()
