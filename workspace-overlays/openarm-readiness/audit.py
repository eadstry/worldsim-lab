"""Bounded read-only image/export audit; never starts simulation or repairs evidence."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import h5py
import numpy as np


def image_metrics(dataset, warmup=30, chunk=8):
    if dataset.dtype != np.uint8 or len(dataset.shape) != 4 or dataset.shape[-1] != 3:
        raise ValueError(f'Expected uint8 NHWC RGB, got {dataset.shape}/{dataset.dtype}')
    if not len(dataset):
        raise ValueError('Empty camera stream')
    means, dark, variation = [], [], []
    for start in range(0, len(dataset), chunk):
        frames = np.asarray(dataset[start:start + chunk])
        axes = (1, 2, 3)
        means.extend(frames.mean(axis=axes).tolist())
        dark.extend((frames <= 2).mean(axis=axes).tolist())
        variation.extend(frames.std(axis=axes).tolist())
    means, dark, variation = map(np.asarray, (means, dark, variation))
    suspected = (means < 1) & (dark > .99)
    after = suspected[min(warmup, len(suspected)):]
    return dict(frames=len(dataset), shape=list(dataset.shape), dtype=str(dataset.dtype),
                mean_intensity_quantiles=np.quantile(means, [0, .01, .5, .99, 1]).tolist(),
                spatial_std_median=float(np.median(variation)),
                suspected_black_frames=int(suspected.sum()),
                suspected_black_fraction=float(suspected.mean()),
                warmup_frames_excluded=min(warmup, len(dataset)),
                post_warmup_frames=len(after),
                post_warmup_suspected_black_fraction=float(after.mean()) if len(after) else None,
                diagnostic_rule='mean < 1/255 AND >99% channel values <=2/255; not a semantic image-validity proof')


def journal_runs(path):
    runs = defaultdict(lambda: dict(events=Counter(), first_utc=None, last_utc=None))
    invalid = 0
    with path.open() as stream:
        for line in stream:
            try:
                row = json.loads(line)
                run_id = row.get('run_id', 'missing')
                run = runs[run_id]
                run['events'][row.get('event', 'missing')] += 1
                timestamp = row.get('time_utc')
                if timestamp:
                    run['first_utc'] = min(run['first_utc'] or timestamp, timestamp)
                    run['last_utc'] = max(run['last_utc'] or timestamp, timestamp)
            except (json.JSONDecodeError, AttributeError, TypeError):
                invalid += 1
    return dict(runs=runs, invalid_lines=invalid)


def export_audit(directory):
    run = json.loads((directory / 'dataset.run.json').read_text())
    export = json.loads((directory / 'dataset.export.json').read_text())
    journal = journal_runs(directory / 'dataset.telemetry.jsonl')
    ids = list(journal['runs'])
    return dict(directory=str(directory), supervisor_run_id=run['run_id'],
                supervisor_status=run['status'], export_status=export['status'],
                completion_error=run.get('completion_error'), export_error=export.get('error'),
                telemetry=journal, multiple_run_ids=len(ids) > 1,
                inference='Multiple runs wrote this telemetry path; shard disappearance cause is not proven by this audit',
                saved_entries=sum(e.get('status') == 'saved' for e in export.get('entries', [])),
                source_immutability='read only; historical files not repaired or deleted')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--export-directory', type=Path, required=True)
    parser.add_argument('--preflight', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    before = args.source.stat()
    result = dict(checked_at=datetime.now(timezone.utc).isoformat(),
                  scope='Full camera pixel scan, historical export journal audit and resource admission; no simulation/training',
                  source=str(args.source.resolve()), source_bytes=before.st_size,
                  script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    probe = subprocess.run([sys.executable, str(args.preflight), '--protocol', str(args.protocol),
                            '--output', str(args.output / 'qualification24')], capture_output=True, text=True)
    (args.output / 'preflight-console.txt').write_text(probe.stdout + probe.stderr)
    if probe.returncode not in (0, 2):
        raise RuntimeError('Resource probe failed; see preflight-console.txt')
    result['qualification24'] = json.loads((args.output / 'qualification24/preflight.json').read_text())
    result['export_audit'] = export_audit(args.export_directory)
    images = {}
    with h5py.File(args.source, 'r') as source:
        for demo_name, demo in source['data'].items():
            images[demo_name] = {}
            for name, dataset in demo['obs'].items():
                if name.endswith('_rgb'):
                    images[demo_name][name] = image_metrics(dataset)
                    print(demo_name, name, json.dumps(images[demo_name][name]), flush=True)
    after = args.source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError('Input changed during audit')
    result['images'] = images
    result['source_size_mtime_unchanged'] = True
    result['status'] = 'audit_complete'
    result['production_ready'] = False
    result['next_gate'] = 'Resolve 24-env memory admission and camera usability before formal capability trials'
    (args.output / 'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print('Audit complete:', args.output / 'audit.json', flush=True)


if __name__ == '__main__':
    main()
