#!/usr/bin/env python3
"""Check pinned source references, sealed artifacts and staged source boundaries."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def git(root, *args):
    # Inspections must not fetch missing objects from partial clones.
    env = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_TERMINAL_PROMPT='0')
    if Path(root).resolve() != ROOT:
        # Hooks inherit the parent index path. It is invalid inside submodules
        # whose .git is a file, and must not leak into read-only source checks.
        for name in ('GIT_INDEX_FILE', 'GIT_DIR', 'GIT_WORK_TREE', 'GIT_COMMON_DIR',
                     'GIT_PREFIX', 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES'):
            env.pop(name, None)
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                          env=env)


def index_entries(root):
    result = git(root, 'ls-files', '--stage', '-z')
    if result.returncode:
        raise ValueError(result.stderr.decode().strip())
    entries = {}
    for record in result.stdout.split(b'\0'):
        if not record:
            continue
        metadata, name = record.decode().split('\t', 1)
        mode, sha, stage = metadata.split()
        if stage != '0':
            raise ValueError(f'Unresolved merge: {name}')
        entries[name] = (mode, sha)
    return entries


def artifact_files(manifest):
    files = manifest['files']
    if isinstance(files, dict):
        return [(name, value if isinstance(value, str) else value['sha256'])
                for name, value in files.items()]
    return [(item['path'], item['sha256']) for item in files]


def check(root, allow_uninitialized=False, require_clean_upstream=False, baseline_ref="HEAD"):
    errors, warnings = [], []
    entries = index_entries(root)
    lock = json.loads((root / 'upstream-lock.json').read_text())
    modules = git(root, 'config', '-f', '.gitmodules', '--get-regexp', r'^submodule\..*\.path$')
    declared = {}
    for line in modules.stdout.decode().splitlines():
        key, path = line.split(None, 1)
        declared[path] = git(root, 'config', '-f', '.gitmodules', '--get',
                             key[:-4] + 'url').stdout.decode().strip()
    gitlinks = {name: sha for name, (mode, sha) in entries.items() if mode == '160000'}
    if set(lock) != set(declared) or set(lock) != set(gitlinks):
        errors.append('Submodule paths differ between lock, .gitmodules and Git index')
    for name, source in lock.items():
        if source['commit'] != gitlinks.get(name):
            errors.append(f'{name}: lock commit differs from Git index')
        if source['url'] != declared.get(name):
            errors.append(f'{name}: lock URL differs from .gitmodules')
        path = root / name
        if not (path / '.git').exists():
            (warnings if allow_uninitialized else errors).append(f'{name}: not initialized')
            continue
        head = git(path, 'rev-parse', 'HEAD').stdout.decode().strip()
        if head != source['commit']:
            errors.append(f'{name}: HEAD {head} differs from lock {source["commit"]}')
        status = git(path, 'status', '--porcelain', '--untracked-files=normal')
        if status.returncode:
            errors.append(f'{name}: cannot inspect worktree: {status.stderr.decode().strip()}')
        elif status.stdout:
            (errors if require_clean_upstream else warnings).append(
                f'{name}: local changes exist (including nested dependencies); inspect git -C {name} status')
        nested = git(path, 'submodule', 'status', '--recursive')
        if nested.returncode:
            errors.append(f'{name}: cannot inspect nested pins')
        for line in nested.stdout.decode().splitlines():
            if line.startswith(('+', 'U')):
                errors.append(f'{name}: nested dependency commit mismatch: {line}')

    count = 0
    manifests = sorted((root / 'outputs').glob('*/*/manifest.json'))
    for path in manifests:
        relative = path.relative_to(root).as_posix()
        try:
            manifest = json.loads(path.read_text())
            for name, expected in artifact_files(manifest):
                member = PurePosixPath(name)
                if member.is_absolute() or '..' in member.parts:
                    raise ValueError(f'Unsafe artifact path: {name}')
                target = path.parent / name
                if relative in entries and target.relative_to(root).as_posix() not in entries:
                    errors.append(f'{relative}: sealed payload absent from Git index: {name}')
                if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                    errors.append(f'{relative}: missing or changed sealed file {name}')
                count += 1
            previous = git(root, 'show', f'{baseline_ref}:{relative}')
            if previous.returncode == 0:
                old = json.loads(previous.stdout)
                # Delivery receipts may evolve; sealed content/provenance must not.
                if old.get('sealed_at') and {k: v for k, v in old.items() if k != 'delivery'} != {
                        k: v for k, v in manifest.items() if k != 'delivery'}:
                    errors.append(f'{relative}: sealed metadata changed; create a new version')
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append(f'{relative}: {error}')
    # A missing whole version would otherwise disappear from glob() silently.
    previous_manifests = git(root, 'ls-tree', '-r', '--name-only', baseline_ref, '--', 'outputs').stdout.decode().splitlines()
    for name in previous_manifests:
        if name.endswith('/manifest.json') and (not (root / name).is_file() or name not in entries):
            errors.append(f'{name}: recorded version deleted; retain sealed snapshots')

    patches = root / 'workspace-overlays/upstream-patches/manifest.json'
    if patches.is_file():
        for record in json.loads(patches.read_text())['repositories']:
            if 'patch' in record:
                p = patches.parent / record['patch']
                if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != record['sha256']:
                    errors.append(f'Upstream patch missing or changed: {record["repository"]}')

    staged = git(root, 'diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z')
    staged_names = {raw.decode() for raw in staged.stdout.split(b'\0') if raw}
    if staged_names:
        metadata_paths = ['upstream-lock.json', '.gitmodules']
        metadata_paths += [p.relative_to(root).as_posix() for p in manifests
                           if any(name.startswith(p.parent.relative_to(root).as_posix() + '/')
                                  for name in staged_names)]
        for name in metadata_paths:
            indexed = git(root, 'show', ':' + name)
            if indexed.returncode or indexed.stdout != (root / name).read_bytes():
                errors.append(f'Version metadata must be staged with its final content: {name}')
    unstaged = set(git(root, 'diff', '--name-only', '--ignore-submodules=all', '-z').stdout.split(b'\0'))
    forbidden_suffixes = {'.h5', '.hdf5', '.pt', '.pth', '.ckpt', '.safetensors', '.pem', '.key'}
    for raw in staged.stdout.split(b'\0'):
        if not raw:
            continue
        name = raw.decode()
        if raw in unstaged:
            errors.append(f'Staged file also has unstaged changes; stage the reviewed final file: {name}')
        p = PurePosixPath(name)
        if (p.suffix in forbidden_suffixes or
                any(part in {'.worktrees', 'framework-dev', '.venv', 'node_modules', '.aws', '.codex'} for part in p.parts) or
                any(part == '.env' or (part.startswith('.env.') and part != '.env.example') for part in p.parts) or
                name.startswith(('runs/', 'config/.local/', 'workspace-overlays/openarm-production/runtime/',
                                 'workspace-overlays/arena-deliveries/', 'workspace-overlays/dev-state-snapshot-'))):
            errors.append(f'Runtime data, machine state or credential file staged: {name}')
    print(f'Checked {len(lock)} upstream pins, {len(manifests)} manifests and {count} sealed files')
    return errors, warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-uninitialized', action='store_true', help='Permit intentionally absent source checkouts')
    parser.add_argument('--require-clean-upstream', action='store_true', help='Fail on upstream worktree changes')
    args = parser.parse_args()
    try:
        errors, warnings = check(ROOT, args.allow_uninitialized, args.require_clean_upstream)
    except (OSError, ValueError, KeyError) as error:
        errors, warnings = [str(error)], []
    for warning in warnings:
        print('WARNING:', warning)
    for error in errors:
        print('ERROR:', error, file=sys.stderr)
    return bool(errors)


if __name__ == '__main__':
    sys.exit(main())
