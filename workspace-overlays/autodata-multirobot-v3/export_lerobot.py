"""Use the official LeRobot v3 writer; validate numeric alignment and decoded videos."""
from pathlib import Path
import argparse, hashlib, importlib.metadata, json, subprocess, os
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['HF_DATASETS_OFFLINE'] = '1'
import numpy as np

def convert(source, output, robot, expected=12):
    import cv2
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    import functools, lerobot.datasets.lerobot_dataset as writer
    from lerobot.datasets.video_utils import encode_video_frames
    writer.encode_video_frames = functools.partial(encode_video_frames, crf=16, g=15)
    episodes = sorted((p for p in source.glob('episode-*') if (p / 'verification.json').exists()))
    if len(episodes) != expected:
        raise ValueError(f'Expected {expected} episodes for {robot}, got {len(episodes)}')
    first = json.loads((episodes[0] / 'verification.json').read_text())
    names = first['joint_names']
    n = len(names)
    features = {'observation.state': dict(dtype='float32', shape=(n,), names=names), 'action': dict(dtype='float32', shape=(n,), names=names), 'next.observation.state': dict(dtype='float32', shape=(n,), names=names), 'observation.cube_positions': dict(dtype='float32', shape=(9,), names=[f'{c}.{axis}' for c in ['red', 'green', 'blue'] for axis in ['x', 'y', 'z']]), 'next.observation.cube_positions': dict(dtype='float32', shape=(9,), names=[f'{c}.{axis}' for c in ['red', 'green', 'blue'] for axis in ['x', 'y', 'z']]), 'observation.images.overview': dict(dtype='video', shape=(1080, 1920, 3), names=['height', 'width', 'channels']), 'domain.condition': dict(dtype='int64', shape=(1,), names=['condition_index'])}
    ds = LeRobotDataset.create(repo_id='local/' + robot + '_home_mini', root=output, robot_type=robot, fps=30, features=features, use_videos=True, image_writer_threads=4, vcodec='h264')
    manifest = []
    for index, path in enumerate(episodes):
        info = json.loads((path / 'verification.json').read_text())
        assert info['success'] and info['joint_names'] == names
        r = np.load(path / 'trajectory.npz')
        np.testing.assert_array_equal(r['next_state'][:-1], r['state'][1:])
        cap = cv2.VideoCapture(str(path / 'overview.mp4'))
        frames = len(r['state'])
        if cap.get(cv2.CAP_PROP_FRAME_WIDTH) != 1920 or cap.get(cv2.CAP_PROP_FRAME_HEIGHT) != 1080 or abs(cap.get(cv2.CAP_PROP_FPS) - 30) > 0.001:
            raise ValueError('Video format mismatch')
        for i in range(frames):
            ok, bgr = cap.read()
            if i and i % 24 == 0:
                ds.image_writer.wait_until_done()
            if not ok:
                raise ValueError(f'Truncated video at {path}/{i}')
            task = 'Pick the ' + info['checks'][0]['color'] + ' cube and place it at its target.' if len(info['checks']) == 1 else 'Pick and arrange the cubes in red, green, blue order.'
            ds.add_frame({'observation.state': r['state'][i].astype(np.float32), 'action': r['action'][i].astype(np.float32), 'next.observation.state': r['next_state'][i].astype(np.float32), 'observation.cube_positions': r['cube_pos'][i].reshape(9).astype(np.float32), 'next.observation.cube_positions': r['next_cube_pos'][i].reshape(9).astype(np.float32), 'observation.images.overview': cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), 'domain.condition': np.array([info['condition']], dtype=np.int64), 'task': task})
        if cap.read()[0]:
            raise ValueError('Video has extra frames')
        cap.release()
        ds.save_episode(parallel_encoding=False)
        manifest.append(dict(episode_index=index, source=str(path.resolve()), source_relative=os.path.relpath(path.resolve(), output.resolve()), frames=frames, verification=info, video_sha256=hashlib.sha256((path / 'overview.mp4').read_bytes()).hexdigest()))
        print('saved', robot, index, frames, flush=True)
    ds.stop_image_writer()
    ds.finalize()
    meta = dict(encoding=dict(codec='H.264', crf=16, gop=15), writer_version=importlib.metadata.version('lerobot'), robot=robot, action_semantics='Absolute joint position targets applied over the next 1/30 second; radians for revolute joints, metres for prismatic joints.', observation_semantics='State and RGB are sampled before the action. next.* is sampled after 40 MuJoCo substeps.', joint_names=names, units=first['units'], episodes=manifest)
    (output / 'meta' / 'generation.json').write_text(json.dumps(meta, indent=2))
    validate(output)

def validate(output):
    import av, cv2, pyarrow as pa, pyarrow.parquet as pq
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    meta = json.loads((output / 'meta' / 'generation.json').read_text())
    rows = pa.concat_tables([pq.read_table(p) for p in sorted((output / 'data').rglob('*.parquet'))]).to_pandas()
    ds = LeRobotDataset('local/' + meta['robot'] + '_home_mini', root=output, video_backend='torchcodec')
    assert ds.num_episodes == len(meta['episodes']) and len(ds) == len(rows)
    samples = []
    video_errors = []
    for ep in meta['episodes']:
        raw = (output / ep['source_relative']).resolve() if 'source_relative' in ep else Path(ep['source'])
        r = np.load(raw / 'trajectory.npz')
        subset = rows[rows.episode_index == ep['episode_index']].sort_values('frame_index')
        assert len(subset) == ep['frames']
        for key, source in [('action', 'action'), ('observation.state', 'state'), ('next.observation.state', 'next_state')]:
            np.testing.assert_array_equal(np.stack(subset[key]), r[source].astype(np.float32))
        for key, source_key in [('observation.cube_positions', 'cube_pos'), ('next.observation.cube_positions', 'next_cube_pos')]:
            np.testing.assert_array_equal(np.stack(subset[key]), r[source_key].reshape(-1, 9).astype(np.float32))
        np.testing.assert_array_equal(subset['domain.condition'].to_numpy(), np.full(ep['frames'], ep['verification']['condition'], dtype=np.int64))
        reference_video = cv2.VideoCapture(str(raw / 'overview.mp4'))
        ok, first_bgr = reference_video.read()
        assert ok
        first_rgb = cv2.cvtColor(first_bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255
        np.testing.assert_array_equal(subset.frame_index.to_numpy(), np.arange(ep['frames']))
        np.testing.assert_allclose(subset.timestamp.to_numpy(), np.arange(ep['frames']) / 30, atol=1e-05, rtol=0)
        for frame in [0, ep['frames'] // 2, ep['frames'] - 1]:
            row = ds[int(subset.iloc[frame]['index'])]
            image = row['observation.images.overview']
            assert tuple(image.shape) == (3, 1080, 1920) and bool(image.isfinite().all())
            samples.append([ep['episode_index'], frame])
            reference_video.set(cv2.CAP_PROP_POS_FRAMES, frame)
            ok, bgr = reference_video.read()
            assert ok
            reference = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255
            actual = image.numpy().transpose(1, 2, 0)
            error = np.abs(actual - reference)
            motion = np.max(np.abs(reference - first_rgb), axis=2) > 0.03
            mae = float(error[motion].mean()) if motion.any() else float(error.mean())
            assert mae < 0.06, f"Video boundary/alignment mismatch {ep['episode_index']}/{frame}: {mae}"
            video_errors.append(mae)
        reference_video.release()
    count = 0
    for path in (output / 'videos').rglob('*.mp4'):
        with av.open(str(path)) as video:
            for frame in video.decode(video=0):
                assert frame.width == 1920 and frame.height == 1080
                count += 1
    assert count == len(ds)
    (output / 'validation.json').write_text(json.dumps(dict(official_loader=True, episodes=len(meta['episodes']), frames=len(ds), all_numeric_rows_exact=True, decoded_frames=count, boundary_samples=samples, maximum_video_motion_region_mae=max(video_errors)), indent=2))
    print('validated', output, len(ds), flush=True)
if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--robot')
    p.add_argument('--expected-episodes', type=int, default=12)
    p.add_argument('--validate', action='store_true')
    a = p.parse_args()
    validate(a.output) if a.validate else convert(a.source, a.output, a.robot, a.expected_episodes)
