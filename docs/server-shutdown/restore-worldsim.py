#!/usr/bin/env python3
"""Verify and restore the untracked/ignored-file overlay from the shutdown Release.
First restore Git checkouts using metadata/worktrees.json and local-history.bundle.
Then run this tool against downloaded Release assets. It never executes archived code.
"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import threading

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--assets-dir', type=Path, required=True)
parser.add_argument('--dest', type=Path, required=True)
args = parser.parse_args()
assets = args.assets_dir.resolve()
dest = args.dest.resolve()
manifest = json.loads((assets / 'manifest.json').read_text())
receipts = [json.loads(p.read_text()) for p in sorted(assets.glob('group-[0-9][0-9][0-9][0-9].json'))]
if not receipts:
    raise SystemExit('No completed group receipts')
parts = []
for receipt in receipts:
    for entry in receipt['parts']:
        path = assets / entry['name']
        with path.open('rb') as handle:
            digest = hashlib.file_digest(handle, 'sha256').hexdigest()
        if digest != entry['sha256'] or path.stat().st_size != entry['bytes']:
            raise SystemExit('Checksum mismatch: ' + path.name)
        parts.append(path)
completed_objects = {d for r in receipts for d in r['objects']}
manifest['files'] = [e for e in manifest['files'] if e.get('sha256') in completed_objects or 'symlink' in e]
by_digest = collections.defaultdict(list)
symlinks = []

def safe_target(rel):
    parts = PurePosixPath(rel)
    if parts.is_absolute() or '..' in parts.parts:
        raise ValueError('Unsafe recovery path')
    target = dest.joinpath(*parts.parts)
    if not target.resolve().is_relative_to(dest):
        raise ValueError('Recovery parent escapes destination')
    return target

for entry in manifest['files']:
    target = safe_target(entry['restore_path'])
    if target.exists() or target.is_symlink():
        raise SystemExit('Refusing to overwrite: ' + str(target))
    if 'sha256' in entry:
        by_digest[entry['sha256']].append(entry)
    else:
        symlinks.append(entry)
proc = subprocess.Popen(['zstd', '-q', '-d', '-c'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
feed_errors = []

def feed():
    try:
        for path in parts:
            with path.open('rb') as handle:
                shutil.copyfileobj(handle, proc.stdin, 4 * 1024 * 1024)
    except BaseException as exc:
        feed_errors.append(str(exc))
    finally:
        proc.stdin.close()

thread = threading.Thread(target=feed)
thread.start()
restored = set()
try:
    with tarfile.open(fileobj=proc.stdout, mode='r|', ignore_zeros=True) as archive:
        for member in archive:
            digest = member.name.removeprefix('objects/')
            if member.name != 'objects/' + digest or digest not in by_digest or not member.isfile():
                raise ValueError('Unexpected archive member: ' + member.name)
            entries = by_digest[digest]
            first = safe_target(entries[0]['restore_path'])
            first.parent.mkdir(parents=True, exist_ok=True)
            check = hashlib.sha256()
            with archive.extractfile(member) as source, first.open('xb') as output:
                while chunk := source.read(4 * 1024 * 1024):
                    output.write(chunk)
                    check.update(chunk)
            if check.hexdigest() != digest:
                first.unlink()
                raise ValueError('Object checksum mismatch: ' + digest)
            for entry in entries:
                target = safe_target(entry['restore_path'])
                if target != first:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with first.open('rb') as source, target.open('xb') as output:
                        shutil.copyfileobj(source, output, 4 * 1024 * 1024)
                os.chmod(target, entry['mode'])
                os.utime(target, ns=(entry['mtime_ns'], entry['mtime_ns']))
            restored.add(digest)
finally:
    proc.stdout.close()
    thread.join()
    rc = proc.wait()
if rc or feed_errors or restored != set(by_digest):
    raise SystemExit('Incomplete archive restoration')
# Create links after regular files, so archived links cannot redirect file writes.
for entry in symlinks:
    target = safe_target(entry['restore_path'])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(entry['symlink'])
print('Restored', len(manifest['files']), 'file paths to', dest)
print('Review external symlink targets and reinstall excluded environments before execution.')
