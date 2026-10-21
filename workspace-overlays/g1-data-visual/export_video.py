# SPDX-License-Identifier: Apache-2.0
"""Export the complete diagnostic camera stream of each generated episode."""
import argparse
import json
from pathlib import Path

import h5py
import imageio_ffmpeg
import numpy as np
from PIL import Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--expected-episodes', type=int, default=1)
    parser.add_argument('--allow-failed', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    result = []
    with h5py.File(args.dataset, 'r') as f:
        sim = json.loads(f['data'].attrs['env_args'])['sim_args']
        fps = 1 / (sim['dt'] * sim['decimation'])
        for name in sorted(f['data'], key=lambda s: int(s.rsplit('_', 1)[-1])):
            episode = f['data'][name]
            frames = episode['overview_rgb']
            assert frames.dtype == np.uint8 and frames.shape[-1] == 3, frames.shape
            count, height, width, _ = frames.shape
            assert count == len(episode['actions']) and count > 0
            output = args.output / f'{name}.mp4'
            writer = imageio_ffmpeg.write_frames(
                str(output), (width, height), fps=fps, codec='libx264',
                pix_fmt_in='rgb24', pix_fmt_out='yuv420p', macro_block_size=1,
                output_params=['-crf', '19', '-preset', 'fast', '-threads', '2', '-movflags', '+faststart'],
            )
            writer.send(None)
            try:
                chunk = frames.chunks[0] if frames.chunks else 32
                for start in range(0, count, chunk):
                    for frame in frames[start:start + chunk]:
                        writer.send(frame)
            finally:
                writer.close()
            for label, idx in [('start', 0), ('middle', count // 2), ('end', count - 1)]:
                Image.fromarray(frames[idx]).save(args.output / f'{name}-{label}.png')
            actual_frames, actual_seconds = imageio_ffmpeg.count_frames_and_secs(str(output))
            assert actual_frames == count, (count, actual_frames)
            result.append(dict(episode=name, success=bool(episode.attrs.get('success', False)),
                               frames=count, fps=fps, seconds=count/fps, verified_video_frames=actual_frames,
                               verified_video_seconds=actual_seconds, video=str(output.resolve())))
            print(result[-1], flush=True)
    (args.output / 'manifest.json').write_text(json.dumps(result, indent=2))
    assert len(result) == args.expected_episodes, result
    assert args.allow_failed or all(r['success'] for r in result), result


if __name__ == '__main__':
    main()
