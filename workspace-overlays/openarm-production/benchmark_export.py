# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Host-only compression comparison on RGB from a CLOSED production HDF5."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path

import h5py


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--demo', default='demo_0')
    parser.add_argument('--frames', type=int, default=32)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    assert args.frames > 0 and args.repeats > 0
    source = args.input.resolve()
    assert source != args.report.resolve()
    assert not args.report.exists(), 'Use a new report path'
    run_file = source.with_suffix('.run.json')
    if run_file.exists():
        run = json.loads(run_file.read_text())
        assert run.get('ended_at'), 'Refusing to read an active/stale run; wait for clean shutdown'
    arrays = {}
    with h5py.File(source, 'r') as dataset:
        demo = dataset[f'data/{args.demo}']

        def read_rgb(name, value):
            if isinstance(value, h5py.Dataset) and 'rgb' in name and value.ndim == 4:
                arrays[name] = (value[:args.frames], value.chunks)

        demo.visititems(read_rgb)
    assert arrays, 'No RGB datasets found; do not substitute synthetic images for production evidence'
    rows = []
    # Same directory/filesystem as production; never touch the source file.
    with tempfile.TemporaryDirectory(prefix='export-benchmark-', dir=source.parent) as directory:
        modes = ('gzip', 'none', 'lzf')
        for repeat in range(args.repeats):
            # Rotate ordering to reduce systematic warm-cache/order bias.
            order = modes[repeat % len(modes):] + modes[:repeat % len(modes)]
            for mode in order:
                target = Path(directory) / f'{repeat}-{mode}.hdf5'
                cpu_start, start = time.thread_time(), time.perf_counter()
                with h5py.File(target, 'w') as output:
                    for name, (array, chunks) in arrays.items():
                        parent, key = name.rsplit('/', 1)
                        chunk_shape = tuple(min(c, s) for c, s in zip(chunks, array.shape)) if chunks else True
                        options = dict(chunks=chunk_shape)
                        if mode != 'none':
                            options['compression'] = mode
                        if mode == 'gzip':
                            options['compression_opts'] = 2
                        output.require_group(parent).create_dataset(key, data=array, **options)
                    create_wall = time.perf_counter() - start
                    create_cpu = time.thread_time() - cpu_start
                    start = time.perf_counter()
                    output.flush()
                    flush_wall = time.perf_counter() - start
                start = time.perf_counter()
                with target.open('rb') as stream:
                    os.fsync(stream.fileno())
                sync_wall = time.perf_counter() - start
                rows.append(dict(repeat=repeat, compression=mode, create_wall_seconds=create_wall,
                                 create_thread_cpu_seconds=create_cpu, flush_wall_seconds=flush_wall,
                                 post_close_fsync_seconds=sync_wall, output_bytes=target.stat().st_size))
                target.unlink()
    report = dict(source=str(source), demo=args.demo, frames=args.frames,
                  datasets={k: dict(shape=list(v.shape), dtype=str(v.dtype), raw_bytes=v.nbytes,
                                    source_chunks=c) for k, (v, c) in arrays.items()}, results=rows,
                  limitations='Offline bounded RGB replay, not full simulation or whole-episode export. '
                              'create includes compression and I/O; no-compression difference is comparative, '
                              'not exact compression time because bytes written differ. Warm page cache is possible. '
                              'fsync is measured separately and is NOT added to production export.')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open('x') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
