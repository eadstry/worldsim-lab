# SPDX-License-Identifier: Apache-2.0
"""Export complete views and compare a small controlled DR production batch."""
import argparse
import hashlib
import json
from pathlib import Path

import h5py
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def export_view(dataset, output, fps):
    count, height, width, _ = dataset.shape
    writer = imageio_ffmpeg.write_frames(str(output), (width, height), fps=fps, codec='libx264',
        pix_fmt_in='rgb24', pix_fmt_out='yuv420p', macro_block_size=1,
        output_params=['-crf', '20', '-preset', 'fast', '-threads', '2', '-movflags', '+faststart'])
    writer.send(None)
    try:
        for start in range(0, count, 32):
            for frame in dataset[start:start + 32]:
                writer.send(frame)
    finally:
        writer.close()
    actual_frames, actual_seconds = imageio_ffmpeg.count_frames_and_secs(str(output))
    assert actual_frames == count, (output, actual_frames, count)
    return dict(path=str(output.resolve()), decoded_frames=actual_frames, decoded_seconds=actual_seconds)


def image_metrics(frames):
    luminance = frames.astype(np.float32) @ np.array([.2126, .7152, .0722], dtype=np.float32)
    return dict(mean_luminance=float(luminance.mean()), dark_fraction=float((luminance <= 5).mean()),
                clipped_fraction=float((luminance >= 250).mean()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plans', type=Path, required=True)
    parser.add_argument('--runs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plans = [json.loads(Path(p).read_text()) for p in json.loads(args.plans.read_text())]
    assert plans and plans[0]['name'] == 'baseline', 'The paired baseline must be first'
    try:
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 17)
    except OSError:
        font = ImageFont.load_default()
    args.output.mkdir(parents=True, exist_ok=False)
    results, tiles = [], []
    baseline_frames = {}
    for plan in plans:
        name = plan['name']
        folder = args.runs / name
        dataset_path = folder / 'episodes.hdf5'
        output = args.output / name
        output.mkdir()
        result = dict(name=name, generation_seed=plan['generation_seed'], randomization_seed=plan['randomization_seed'],
                      active=plan['active'], sampled=plan['sampled'], dataset=str(dataset_path.resolve()),
                      dataset_sha256=hashlib.sha256(dataset_path.read_bytes()).hexdigest())
        with h5py.File(dataset_path) as f:
            assert list(f['data']) == ['demo_0'], list(f['data'])
            e = f['data/demo_0']
            sim = json.loads(f['data'].attrs['env_args'])['sim_args']
            fps = 1.0 / (sim['dt'] * sim['decimation'])
            count = len(e['actions'])
            trace = np.asarray(e['dr_success_observed'][:]).reshape(-1)
            assert len(trace) == count
            indices = np.unique(np.linspace(0, count - 1, 8).astype(int))
            overview = e['overview_rgb'][indices]
            head = e['camera_obs/robot_head_cam_rgb'][indices]
            assert count == len(e['overview_rgb']) == len(e['camera_obs/robot_head_cam_rgb'])
            # Compare the same control step, rather than time-normalizing different trajectories.
            matched = min(400, count - 1)
            comparison = {'overview': e['overview_rgb'][matched], 'head': e['camera_obs/robot_head_cam_rgb'][matched]}
            if name == 'baseline':
                baseline_frames = comparison
            result.update(success=bool(e.attrs['success']), frames=count, fps=fps, seconds=count/fps,
                finite_actions=bool(np.isfinite(e['actions'][:]).all()),
                initial_box_pose=e['initial_state/rigid_object/brown_box/root_pose'][:].tolist(),
                final_box_speed_m_s=float(np.linalg.norm(e['states/rigid_object/brown_box/root_velocity'][-1, :3])),
                first_recorded_success_step=int(np.flatnonzero(trace)[0]) if trace.any() else None,
                overview=image_metrics(overview), head=image_metrics(head))
            result['matched_step'] = matched
            result['matched_step_rgb_mae_255'] = {view: float(np.abs(frame.astype(float) - baseline_frames[view]).mean())
                                                 for view, frame in comparison.items()}
            result['overview_video'] = export_view(e['overview_rgb'], output / 'overview.mp4', fps)
            if name in ('baseline', 'camera', 'combined_s1', 'combined_s2', 'pose_wide') or 'camera' in plan['sampled']:
                result['head_video'] = export_view(e['camera_obs/robot_head_cam_rgb'], output / 'head.mp4', fps)
            for label, index in [('start', 0), ('middle', count//2), ('end', count-1)]:
                Image.fromarray(e['overview_rgb'][index]).save(output / f'overview-{label}.png')
                Image.fromarray(e['camera_obs/robot_head_cam_rgb'][index]).save(output / f'head-{label}.png')
            tile = Image.new('RGB', (640, 300), '#17212b')
            ImageDraw.Draw(tile).text((8, 5), f'{name} | seed {plan["generation_seed"]} | success={result["success"]}', fill='white', font=font)
            tile.paste(Image.fromarray(comparison['overview']).resize((320, 180)), (0, 25))
            tile.paste(Image.fromarray(comparison['head']).resize((320, 240)), (320, 25))
            tiles.append(tile)
        result['resolved'] = json.loads((folder / 'dr-resolved.json').read_text())
        result['readback'] = json.loads((folder / 'dr-readback.json').read_text())
        if 'camera' in plan['sampled']:
            baseline_k = np.asarray(results[0]['readback']['camera_intrinsics'])
            actual_k = np.asarray(result['readback']['camera_intrinsics'])
            expected_scale = plan['sampled']['camera']['focal_scale']
            ratios = [float(actual_k[0, 0] / baseline_k[0, 0]), float(actual_k[1, 1] / baseline_k[1, 1])]
            assert np.allclose(ratios, expected_scale, rtol=1e-4), (ratios, expected_scale)
            result['verified_focal_scale_xy'] = ratios
        if 'lighting' in plan['sampled']:
            assert plan['hdr'] in result['readback']['hdr'], 'HDR path readback differs'
            assert np.isclose(result['readback']['key_temperature_k'], plan['sampled']['lighting']['temperature_k'], rtol=1e-5)
        results.append(result)
        print(json.dumps({k: result[k] for k in ('name', 'success', 'frames', 'final_box_speed_m_s')}), flush=True)
    board = Image.new('RGB', (1280, 300 * ((len(tiles) + 1)//2)), '#17212b')
    for index, tile in enumerate(tiles):
        board.paste(tile, ((index % 2)*640, (index//2)*300))
    board.save(args.output / 'comparison.png')
    summary = dict(episodes=results, num_attempts=len(results), num_success=sum(r['success'] for r in results),
                   scope='Production feasibility and appearance checks; not learned-policy or real-world generalization.',
                   warning='Paired generation seeds aid comparison; one sample per single-factor profile is not a success-rate estimate.')
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
