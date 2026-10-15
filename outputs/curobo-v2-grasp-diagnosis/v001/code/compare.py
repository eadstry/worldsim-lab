# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Check paired initial states before interpreting single-arm backend comparisons."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from summarize import summarize


def maximum_error(left, right) -> float:
    if isinstance(left, dict):
        assert left.keys() == right.keys(), 'Initial object identities differ'
        return max((maximum_error(left[k], right[k]) for k in left), default=0)
    if isinstance(left, list):
        assert len(left) == len(right), 'Initial state dimensions differ'
        return max((maximum_error(a, b) for a, b in zip(left, right)), default=0)
    return abs(float(left) - float(right))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('v1', type=Path)
    parser.add_argument('v2', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    reports = [summarize(args.v1), summarize(args.v2)]
    assert [r['backend'] for r in reports] == ['v1', 'v2']
    assert all(r['status'] == 'completed' and r['uncontended'] and not r['smoke'] and not r['diagnostics'] for r in reports)
    assert reports[0]['attempts'] == reports[1]['attempts'] and reports[0]['attempts'] > 0
    pairs = []
    for a, b in zip(reports[0]['initial_states'], reports[1]['initial_states']):
        assert a['seed'] == b['seed'] and a['episode_index'] == b['episode_index']
        objects = maximum_error(a['object_poses'], b['object_poses'])
        joints = maximum_error(a['joint_positions'], b['joint_positions'])
        pairs.append(dict(seed=a['seed'], object_matrix_max_absolute_error=objects,
                          joint_max_absolute_error=joints, matched=objects <= 1e-6 and joints <= 1e-6))
    assert len(pairs) == reports[0]['attempts'], 'Missing reset observations'
    result = dict(schema_version=1, runs=reports, initial_state_pairs=pairs,
                  paired_initial_states_match=all(p['matched'] for p in pairs))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(paired_initial_states_match=result['paired_initial_states_match'], pairs=pairs), indent=2))


if __name__ == '__main__':
    main()
