# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Verify the original environment guard, input identity and generated HDF5 readback."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open('rb') as file:
        for block in iter(lambda: file.read(2**20), b''):
            checksum.update(block)
    return checksum.hexdigest()


def readback(path: Path) -> dict:
    """Read actions and metadata without materializing large image arrays."""
    import h5py
    import numpy as np

    episodes = []
    with h5py.File(path, 'r') as file:
        assert 'data' in file
        for name, episode in file['data'].items():
            actions = episode['actions']
            assert actions.ndim == 2 and actions.shape[1] == 7 and len(actions) > 0
            assert np.isfinite(actions[:]).all()
            assert int(episode.attrs['num_samples']) == len(actions)
            success = bool(episode.attrs['success'])
            assert success == (not path.stem.endswith('_failed')), 'Episode success attribute and output file disagree'
            episodes.append(dict(name=name, frames=len(actions), action_shape=list(actions.shape), success=success))
    return dict(file=path.name, sha256=digest(path), episodes=episodes,
                episode_count=len(episodes), actions_finite=True, metadata_consistent=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, nargs='*', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    cfg = json.loads((root / '.local/machine.json').read_text())
    guard = json.loads((root / '.local/v1-environment-guard.json').read_text())
    changed = [Path(path).name for path, value in guard.items()
               if not Path(path).is_file() or digest(Path(path)) != value]
    assert not changed, f'Protected v1 files changed: {changed}'
    site = Path(cfg['v1_python']).parents[1] / 'lib/python3.12/site-packages'
    expected_distributions = {path for path in guard if path.endswith('/METADATA')}
    current_distributions = {str(path) for path in site.glob('*.dist-info/METADATA')}
    assert expected_distributions == current_distributions, 'Original installed distribution set changed'
    result = dict(v1_guard_files=len(guard), v1_guard_unchanged=True,
                  v1_distribution_set_unchanged=True,
                  input_sha256=digest(Path(cfg['input'])), runs=[])
    for directory in args.runs:
        launch = json.loads((directory / 'launch.json').read_text())
        stats = json.loads((directory / 'episodes.result.json').read_text())
        assert launch['status'] == 'completed' and launch['returncode'] == 0
        files = [readback(path) for path in directory.glob('episodes*.hdf5')]
        assert sum(item['episode_count'] for item in files) == stats['num_attempts']
        successes = sum(item['episode_count'] for item in files if item['file'] == 'episodes.hdf5')
        assert successes == stats['num_success']
        result['runs'].append(dict(name=directory.name, backend=launch['backend'],
                                   attempts=stats['num_attempts'], successes=successes, hdf5=files))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
