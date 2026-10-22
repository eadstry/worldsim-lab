# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Export and fully decode both recorded wrist streams without resimulation or trimming."""
import argparse
import hashlib
import json
from pathlib import Path

import h5py
import imageio_ffmpeg
import numpy as np
from PIL import Image


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def export(input_path, output):
    output.mkdir(parents=True, exist_ok=False)
    digest = sha256(input_path)
    report = {'input': str(input_path.resolve()), 'input_sha256': digest, 'streams': {},
              'scope': 'Original production RGB frames, H.264 encoding only; no resimulation, frame trimming or interpolation'}
    with h5py.File(input_path, 'r') as source:
        assert list(source['data']) == ['demo_0'], 'Expected the single generated GS episode'
        demo = source['data/demo_0']
        assert bool(demo.attrs['success']), 'Expected a successful generated episode'
        report['env_args'] = json.loads(source['data'].attrs['env_args'])
        steps = len(demo['actions'])
        for side in ('left', 'right'):
            key = side + '_hand_rgb'
            images = demo['obs/' + key]
            assert images.shape == (steps, 480, 640, 3) and images.dtype == np.uint8
            path = output / (side + '-wrist.mp4')
            writer = imageio_ffmpeg.write_frames(str(path), (640, 480), fps=30, codec='libx264',
                pix_fmt_in='rgb24', pix_fmt_out='yuv420p', output_params=['-crf', '18'])
            writer.send(None)
            low_detail = 0
            pixel_sum = 0.0
            try:
                # Read an entire time chunk once; frame reads repeatedly decompress
                # the package's (165,30,40,1) chunks with h5py's default cache.
                batch_size = images.chunks[0] if images.chunks else 32
                for begin in range(0, steps, batch_size):
                    batch = images[begin:begin + batch_size]
                    for offset, frame in enumerate(batch):
                        i = begin + offset
                        writer.send(frame)
                        low_detail += int(frame.std() < 1.0)
                        pixel_sum += float(frame.mean())
                        if i in (0, 500, 1000, 2400):
                            Image.fromarray(frame).save(output / f'{side}-{i:04d}.png')
            finally:
                writer.close()
            reader = imageio_ffmpeg.read_frames(str(path), pix_fmt='rgb24')
            metadata = next(reader)
            decoded = sum(1 for _ in reader)
            assert decoded == steps and metadata['size'] == (640, 480) and metadata['fps'] == 30
            report['streams'][side] = {'dataset': key, 'frames': steps, 'decoded_frames': decoded,
                'fps': 30, 'resolution': [640, 480], 'duration_s': steps/30,
                'low_detail_frames_std_below_1': low_detail, 'mean_pixel_value': pixel_sum/steps,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'metadata': metadata}
            print(side, json.dumps(report['streams'][side]), flush=True)
    assert sha256(input_path) == digest, 'Input changed during export'
    (output / 'wrist-check.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    export(args.input, args.output)
