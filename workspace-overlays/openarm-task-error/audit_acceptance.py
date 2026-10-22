# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Compare original velocity-based acceptance with independently derived pose stability."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def quaternion_speed(quaternions: np.ndarray, dt: float) -> np.ndarray:
    """Shortest rotation magnitude between consecutive XYZW quaternions [rad/s]."""
    q = np.asarray(quaternions, dtype=np.float64)
    q = q / np.linalg.norm(q, axis=-1, keepdims=True)
    dot = np.abs(np.sum(q[1:]*q[:-1], axis=-1))
    return 2*np.arccos(np.clip(dot, 0, 1))/dt


def first_hold(flags: np.ndarray, frames: int = 15) -> int | None:
    count = 0
    for i, flag in enumerate(flags):
        count = count+1 if flag else 0
        if count >= frames:
            return i
    return None


def audit_trial(arrays) -> dict:
    pos = np.asarray(arrays['cube_position'], dtype=np.float64)
    dt = 1/30
    linear = np.r_[np.nan, np.linalg.norm(np.diff(pos, axis=0), axis=-1)/dt]
    angular = np.r_[np.nan, quaternion_speed(arrays['cube_quaternion'], dt)]
    lifted = np.maximum.accumulate(pos[:, 2]) >= pos[0, 2]+.03
    released = (arrays['phase']==3) & (arrays['source_action'][:,-1]>0) & (arrays['post'][:,7:].min(-1)>=.3)
    common = lifted & released
    original = common & arrays['placed']
    observable = common & arrays['geometry_placed'] & (linear<=.03) & (angular<=.5)
    original_index = first_hold(original)
    observable_index = first_hold(observable)
    report_linear = np.linalg.norm(arrays['cube_velocity'],axis=-1)
    report_angular = np.linalg.norm(arrays['cube_angular_velocity'],axis=-1)
    return {'original_pass': original_index is not None, 'pose_stability_pass': observable_index is not None,
            'original_first_time_s': (original_index+1)*dt if original_index is not None else None,
            'pose_stability_status': ('confirmed' if observable_index is not None else 'not_confirmed_before_original_stop' if original_index is not None else 'not_confirmed_at_timeout_or_fall'),
            'pose_stability_first_time_s': (observable_index+1)*dt if observable_index is not None else None,
            'last_second_geometry_fraction': float(np.mean(arrays['geometry_placed'][-30:])),
            'last_second_position_span_mm': (np.ptp(pos[-31:],axis=0)*1000).tolist(),
            'last_second_reported_linear_median_m_s': float(np.median(report_linear[-30:])),
            'last_second_derived_linear_median_m_s': float(np.nanmedian(linear[-30:])),
            'last_second_reported_angular_median_rad_s': float(np.median(report_angular[-30:])),
            'last_second_derived_angular_median_rad_s': float(np.nanmedian(angular[-30:]))}


def audit_directory(path: Path) -> list:
    results=[]
    trials=json.loads((path/'trials.json').read_text())
    for trial in trials:
        name=f"{trial['variant']}-{trial['demo']}-r{trial['repeat']}.npz"
        with np.load(path/name,allow_pickle=False) as arrays:
            item=audit_trial(arrays)
        assert item['original_pass']==trial['success'],name
        item.update(variant=trial['variant'],demo=trial['demo'],repeat=trial['repeat'],file=name)
        results.append(item)
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    results={p.name:audit_directory(p) for p in sorted(args.root.iterdir()) if (p/'complete.json').exists() and (p/'diagnostic-integration.json').exists()}
    args.output.write_text(json.dumps(results,indent=2))
    for key,rows in results.items():
        print(key,'original',sum(r['original_pass'] for r in rows),'/',len(rows),
              'original failures with confirmed pose stability',sum(not r['original_pass'] and r['pose_stability_pass'] for r in rows),
              'pose check censored at original stop',sum(r['pose_stability_status']=='not_confirmed_before_original_stop' for r in rows))
