# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Audit final physics-step pose changes only for tasks active until batch timeout."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from audit_acceptance import quaternion_speed


def audit(root: Path) -> dict:
    rows, hashes = [], {}
    for receipt in sorted(root.glob('*/complete.json')):
        directory = receipt.parent
        if not (directory/'diagnostic-integration.json').exists():
            continue
        trials = json.loads((directory/'trials.json').read_text())
        for path in sorted(directory.glob('cube-physics-r*.npz')):
            hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
            repeat = int(path.stem.split('-r')[-1])
            with np.load(path, allow_pickle=False) as z:
                dt = float(z['physics_dt'])
                values, assignments = z['values'], z['assignments']
            by_key = {(t['variant'],t['demo']):t for t in trials if t['repeat']==repeat}
            for i, (variant, demo) in enumerate(assignments):
                trial = by_key[(str(variant),str(demo))]
                # Early successes/falls keep simulating in the batch. Their final buffer
                # is outside the task window and is intentionally never interpreted.
                if trial['end_reason']!='timeout':
                    continue
                x = values[:, i].astype(np.float64)
                lin = np.linalg.norm(np.diff(x[:,:3],axis=0),axis=-1)/dt
                ang = quaternion_speed(x[:,3:7],dt)
                n = min(len(lin),int(round(1/dt)))
                rows.append(dict(batch=directory.name, variant=str(variant), demo=str(demo), repeat=repeat,
                    physics_dt=dt, samples=n,
                    reported_linear_median_m_s=float(np.median(np.linalg.norm(x[-n:,7:10],axis=-1))),
                    derived_linear_median_m_s=float(np.median(lin[-n:])),
                    derived_linear_max_m_s=float(np.max(lin[-n:])),
                    reported_angular_median_rad_s=float(np.median(np.linalg.norm(x[-n:,10:13],axis=-1))),
                    derived_angular_median_rad_s=float(np.median(ang[-n:])),
                    derived_angular_max_rad_s=float(np.max(ang[-n:])),
                    derived_angular_below_threshold_fraction=float(np.mean(ang[-n:]<=.5)),
                    derived_linear_below_threshold_fraction=float(np.mean(lin[-n:]<=.03)),
                    position_span_mm=(np.ptp(x[-n-1:,:3],axis=0)*1000).tolist()))
    return dict(timeout_trials=rows, source_sha256=hashes,
                scope='Final one second of per-physics-step buffer; timeout attempts only; original acceptance unchanged.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=audit(args.root)
    args.output.write_text(json.dumps(result,indent=2))
    print(len(result['timeout_trials']),'timeout windows audited')
