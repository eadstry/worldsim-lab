# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Aggregate complete-task attempts without filtering failed or missing phases."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np


def condition(args, variant):
    if args['physics_hz'] != 120:
        return f"physics_{args['physics_hz']}"
    if args['position_iterations'] != 16:
        return f"position_{args['position_iterations']}"
    if args['velocity_iterations'] != 4:
        return f"velocity_{args['velocity_iterations']}"
    if args['external_forces_every_iteration']:
        return 'external_forces_every_iteration'
    return variant


def aggregate(root: Path):
    groups = defaultdict(list)
    evidence = {}
    for receipt in sorted(root.glob('*/complete.json')):
        directory = receipt.parent.resolve()
        provenance = json.loads((directory/'provenance.json').read_text())
        args = provenance['args']
        assert args['max_frames'] is None, directory
        assert not (directory/'error.txt').exists()
        trials_path = directory/'trials.json'
        trials = json.loads(trials_path.read_text())
        assert len(trials) == json.loads(receipt.read_text())['trials']
        evidence[str(trials_path)] = hashlib.sha256(trials_path.read_bytes()).hexdigest()
        for trial in trials:
            trial = {**trial, 'directory': str(directory)}
            groups[condition(args, trial['variant'])].append(trial)
    baseline = {(r['demo'], r['repeat']): r for r in groups['baseline']}
    result = {}
    for key, trials in groups.items():
        pairs = [(t, baseline[(t['demo'], t['repeat'])]) for t in trials]
        assert len({(r['demo'], r['repeat']) for r in trials}) == len(trials), key
        successful = [r for r in trials if r['success']]
        values = np.array([r['request_pre']['mae_deg'] for r in trials])
        result[key] = {
            'attempts': len(trials), 'successes': len(successful),
            'success_fraction': len(successful)/len(trials),
            'all_attempt_mean_mae_deg': float(values.mean()),
            'all_attempt_mae_range_deg': [float(values.min()), float(values.max())],
            'successful_attempt_mean_mae_deg': float(np.mean([r['request_pre']['mae_deg'] for r in successful])) if successful else None,
            'mean_trial_p95_deg': float(np.mean([r['request_pre']['p95_deg'] for r in trials])),
            'mean_duration_s': float(np.mean([r['duration_s'] for r in trials])),
            'success_duration_s': float(np.mean([r['duration_s'] for r in successful])) if successful else None,
            'mean_ee_p95_mm': float(np.mean([r['ee_tracking_p95_mm'] for r in trials])),
            'paired_mean_delta_deg': float(np.mean([t['request_pre']['mae_deg']-b['request_pre']['mae_deg'] for t,b in pairs])),
            'paired_mean_change_percent': float(np.mean([(t['request_pre']['mae_deg']/b['request_pre']['mae_deg']-1)*100 for t,b in pairs])),
            'phases': {},
            'end_reasons': {reason: sum(r['end_reason']==reason for r in trials) for reason in set(r['end_reason'] for r in trials)},
            'trials': trials,
        }
        for phase in ['approach','grasp_lift','transport','release_settle']:
            measured = [r['phases'][phase]['mae_deg'] for r in trials if r['phases'][phase]['frames']]
            result[key]['phases'][phase] = {'reached': len(measured),
                'attempt_mean_mae_deg': float(np.mean(measured)) if measured else None}
        for field in ['physics_request_applied_mae_deg', 'physics_applied_pre_mae_deg', 'physics_applied_post_mae_deg']:
            result[key][field] = float(np.mean([r[field] for r in trials]))
    return {'conditions': result, 'evidence_sha256': evidence,
            'aggregation': 'Equal weight per attempt; successful-only results separate; matched initial state/repeat comparisons; descriptive range is not a confidence interval.'}


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args=p.parse_args()
    result=aggregate(args.root)
    args.output.write_text(json.dumps(result, indent=2))
    for key,c in result['conditions'].items():
        print(key, f"{c['successes']}/{c['attempts']}", round(c['all_attempt_mean_mae_deg'],4), round(c['mean_duration_s'],2))
