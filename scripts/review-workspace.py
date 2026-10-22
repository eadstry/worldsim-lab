#!/usr/bin/env python3
"""Review exact task snapshots and install shared commit/push gates. Host checks only."""
import argparse
import ast
from datetime import datetime, timezone
import fnmatch
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys

SCRIPT = Path(__file__).resolve()
ZERO = '0' * 40


def git(root, *args, check=True):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True)
    if check and result.returncode:
        raise ValueError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip() if check else result


def policy(root):
    path = root / 'config/version-policy.json'
    if not path.is_file():
        path = SCRIPT.with_name('version-policy.json')
    return json.loads(path.read_text())


def branch_gate(root, rules):
    branch = git(root, 'symbolic-ref', '--quiet', '--short', 'HEAD', check=False)
    if branch.returncode:
        raise ValueError('Detached HEAD: create a task branch from the integration baseline first')
    branch = branch.stdout.strip()
    if any(fnmatch.fnmatchcase(branch, p) for p in rules['protected_branches']):
        raise ValueError('Direct automatic commits/pushes to protected branches are blocked; use a PR')
    if not branch.startswith(rules['branch_prefix']):
        raise ValueError('Task branch must start with ' + rules['branch_prefix'])
    ancestor = git(root, 'merge-base', '--is-ancestor', rules['required_ancestor'], 'HEAD', check=False)
    if ancestor.returncode:
        raise ValueError('Old task baseline: preserve current work and migrate to the integration baseline')
    if not all((root / name).is_file() for name in ['scripts/check-version-management.py', 'config/version-policy.json']):
        raise ValueError('Worktree lacks version checks; migrate its baseline before committing')
    return branch


def paths(root, base=None):
    args = ['diff', '--name-only', '-z', '--no-renames']
    args += [base, 'HEAD'] if base else ['--cached']
    return [p for p in git(root, *args).split('\0') if p]


def clean_worktree(root):
    # Tests run from the working tree. Never validate uncommitted content that
    # differs from the reviewed index, or accidentally include unrelated work.
    if git(root, 'diff', '--name-only', '--ignore-submodules=all'):
        raise ValueError('Tracked unstaged changes exist; stage the task or use a clean task worktree')
    if git(root, 'ls-files', '--others', '--exclude-standard'):
        raise ValueError('Untracked files exist; explicitly stage task files or use a clean task worktree')


def path_gate(names):
    forbidden = {'.h5', '.hdf5', '.pt', '.pth', '.ckpt', '.safetensors', '.pem', '.key'}
    components = {'.local', '.venv', 'node_modules', '.aws', '.codex', '.worktrees', '__pycache__'}
    for name in names:
        p = PurePosixPath(name)
        if (p.suffix in forbidden or components.intersection(p.parts)
                or any(x == '.env' or (x.startswith('.env.') and x != '.env.example') for x in p.parts)
                or name.startswith(('runs/', 'framework-dev/', 'config/.local/'))
                or ('runtime' in p.parts and name.startswith('workspace-overlays/'))):
            raise ValueError('Runtime data or machine state in review: ' + name)
        if name in {'AutoData', 'IsaacLab-Arena', 'RLinf', 'upstream-lock.json', '.gitmodules'}:
            raise ValueError('Upstream pin updates require a separately authorized dependency change')


def static_review(root, names, base='HEAD', allow_uninitialized=False):
    path_gate(names)
    spec = importlib.util.spec_from_file_location('version_guard', SCRIPT.with_name('check-version-management.py'))
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    guard.ROOT = root
    errors, warnings = guard.check(root, allow_uninitialized=allow_uninitialized,
                                   require_clean_upstream=True, baseline_ref=base)
    for warning in warnings:
        print('WARNING:', warning)
    if errors:
        raise ValueError('\n'.join(errors))
    for name in names:
        path = root / name
        if path.is_file() and path.suffix == '.py':
            ast.parse(path.read_text(), filename=name)
    # Existing sealed payloads retain their original generated whitespace.
    args = ['diff', '--check', base, 'HEAD'] if base != 'HEAD' else ['diff', '--cached', '--check']
    result = git(root, *args, '--', '.', ':(exclude)outputs/**', check=False)
    if result.returncode:
        raise ValueError(result.stdout.strip() or result.stderr.strip())


def receipt_path(root):
    return Path(git(root, 'rev-parse', '--path-format=absolute', '--git-path', 'workspace-review.json'))


def identity(root):
    return {'head': git(root, 'rev-parse', 'HEAD'), 'tree': git(root, 'write-tree'),
            'branch': git(root, 'symbolic-ref', '--short', 'HEAD')}


def run_check(root, command, checks):
    print('CHECK:', shlex.join(command), flush=True)
    result = subprocess.run(command, cwd=root)
    if result.returncode:
        raise ValueError('Required check failed: ' + shlex.join(command))
    checks.append({'command': command, 'status': 'passed'})


def prepare(root, note, allow_uninitialized=False, large_change_reason=None):
    rules = policy(root)
    branch_gate(root, rules)
    receipt_path(root).unlink(missing_ok=True)
    clean_worktree(root)
    names = paths(root)
    if not names:
        raise ValueError('No staged task changes')
    if not note.strip():
        raise ValueError('Record a substantive diff review note before automatic submission')
    if len(names) > rules['large_change_files'] and not large_change_reason:
        raise ValueError('Large change: split commits or supply --large-change-reason')
    static_review(root, names, allow_uninitialized=allow_uninitialized)
    before = identity(root)
    checks = []
    command = ['bash', 'scripts/cloud-check.sh']
    if allow_uninitialized:
        command.append('--allow-uninitialized')
    run_check(root, command, checks)
    suites = [
        ('workspace-overlays/openarm-production/', 'workspace-overlays/openarm-production', 'test_*.py', 'WORLDSIM_REVIEW_PYTHON'),
        ('workspace-overlays/curobo-v2-mvp/', 'workspace-overlays/curobo-v2-mvp', 'test_host.py', 'WORLDSIM_V2_REVIEW_PYTHON'),
        ('workspace-overlays/openarm-v1-timing/', 'workspace-overlays/openarm-v1-timing', 'test_internal_timing.py', 'WORLDSIM_REVIEW_PYTHON'),
        ('workspace-overlays/openarm-throughput-benchmark/', 'workspace-overlays/openarm-throughput-benchmark', 'test_*.py', 'WORLDSIM_REVIEW_PYTHON'),
        ('workspace-overlays/openarm-benchmark/', 'workspace-overlays/openarm-benchmark/tests', 'test_*.py', 'WORLDSIM_REVIEW_PYTHON'),
    ]
    for prefix, folder, pattern, variable in suites:
        if any(n.startswith(prefix) and n.endswith('.py') for n in names):
            run_check(root, [os.environ.get(variable, sys.executable), '-B', '-m', 'unittest',
                             'discover', '-s', folder, '-p', pattern, '-v'], checks)
    clean_worktree(root)
    if identity(root) != before:
        raise ValueError('HEAD/index changed during checks; review the final snapshot again')
    static_review(root, names, allow_uninitialized=allow_uninitialized)
    receipt = dict(before, schema_version=1, review_note=note, checks=checks,
                   allow_uninitialized=allow_uninitialized, large_change_reason=large_change_reason,
                   scope='Host checks and recorded diff self-review; no independent AI/human approval or GPU validation',
                   reviewed_at=datetime.now(timezone.utc).isoformat())
    target = receipt_path(root)
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(target)
    print('PASS: exact staged snapshot reviewed; receipt:', target)


def verify(root, committed=False):
    branch_gate(root, policy(root))
    clean_worktree(root)
    path = receipt_path(root)
    if not path.is_file():
        raise ValueError('Missing review receipt; run review-workspace.py prepare first')
    receipt = json.loads(path.read_text())
    if not receipt.get('review_note') or not receipt.get('checks'):
        raise ValueError('Incomplete review receipt')
    if any(c.get('status') != 'passed' for c in receipt['checks']):
        raise ValueError('Review contains failed checks')
    current = identity(root)
    if receipt['tree'] != current['tree'] or receipt['branch'] != current['branch']:
        raise ValueError('Review is stale: staged content or branch changed')
    if committed:
        if git(root, 'rev-parse', 'HEAD^{tree}') != receipt['tree']:
            raise ValueError('HEAD differs from reviewed tree')
        if receipt['head'] not in git(root, 'rev-list', '--parents', '-n', '1', 'HEAD').split()[1:]:
            raise ValueError('Current commit was not made from the reviewed parent')
    elif receipt['head'] != current['head']:
        raise ValueError('Review is stale: HEAD changed')
    static_review(root, paths(root), allow_uninitialized=receipt['allow_uninitialized'])


def push_gate(root, remote, url, lines):
    rules = policy(root)
    if remote != rules['remote'] or url.rstrip('/') != rules['remote_url']:
        raise ValueError('Automatic push is limited to the configured workspace origin')
    verify(root, committed=True)
    branch = git(root, 'symbolic-ref', '--short', 'HEAD')
    records = [line.split() for line in lines.splitlines() if line.strip()]
    for local_ref, local_sha, remote_ref, remote_sha in records:
        if local_ref != 'refs/heads/' + branch or remote_ref != local_ref:
            raise ValueError('Only the reviewed current task branch may be pushed')
        if local_sha != git(root, 'rev-parse', 'HEAD'):
            raise ValueError('Push target differs from reviewed HEAD')
        if remote_sha != ZERO and git(root, 'merge-base', '--is-ancestor', remote_sha, local_sha, check=False).returncode:
            raise ValueError('Non-fast-forward or unknown remote history; fetch and review, never force-push')


def install(root):
    branch_gate(root, policy(root))
    common = Path(git(root, 'rev-parse', '--path-format=absolute', '--git-common-dir'))
    folder = common / 'workspace-hooks'
    folder.mkdir(exist_ok=True)
    for source, name in [(SCRIPT, 'review-workspace.py'),
                         (SCRIPT.with_name('check-version-management.py'), 'check-version-management.py'),
                         (root / 'config/version-policy.json', 'version-policy.json')]:
        shutil.copy2(source, folder / name)
    for name, action in [('pre-commit', 'verify-index'), ('pre-push', 'verify-push')]:
        text = '#!/usr/bin/env bash\nset -euo pipefail\n'
        text += 'root="$(git rev-parse --show-toplevel)"\n'
        text += 'exec python3 ' + shlex.quote(str(folder / 'review-workspace.py')) + ' --root "$root" ' + action + ' "$@"\n'
        target = folder / name
        target.write_text(text)
        target.chmod(0o755)
    git(root, 'config', '--local', 'core.hooksPath', str(folder))
    git(root, 'config', '--local', 'pull.ff', 'only')
    git(root, 'config', '--local', 'fetch.prune', 'true')
    git(root, 'config', '--local', 'push.default', 'simple')
    print('Installed shared hooks for all worktrees:', folder)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    actions = parser.add_subparsers(dest='action', required=True)
    prep = actions.add_parser('prepare')
    prep.add_argument('--review-note', required=True)
    prep.add_argument('--large-change-reason')
    prep.add_argument('--allow-uninitialized', action='store_true')
    actions.add_parser('verify-index')
    push = actions.add_parser('verify-push')
    push.add_argument('remote')
    push.add_argument('url')
    actions.add_parser('install')
    start = actions.add_parser('start')
    start.add_argument('name')
    start.add_argument('--base')
    finish = actions.add_parser('finish')
    finish.add_argument('--message', required=True)
    finish.add_argument('--review-note', required=True)
    finish.add_argument('--allow-uninitialized', action='store_true')
    finish.add_argument('--large-change-reason')
    finish.add_argument('files', nargs='+')
    ci = actions.add_parser('ci')
    ci.add_argument('--base', required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.action == 'prepare':
        prepare(root, args.review_note, args.allow_uninitialized, args.large_change_reason)
    elif args.action == 'verify-index':
        verify(root)
    elif args.action == 'verify-push':
        push_gate(root, args.remote, args.url, sys.stdin.read())
    elif args.action == 'install':
        install(root)
    elif args.action == 'start':
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', args.name):
            raise ValueError('Use a lowercase task name with letters, digits and hyphens')
        rules = policy(root)
        base = args.base or rules['default_start_ref']
        if git(root, 'merge-base', '--is-ancestor', rules['required_ancestor'], base, check=False).returncode:
            raise ValueError('Selected base does not include the required integration baseline')
        if git(root, 'cat-file', '-e', base + ':config/version-policy.json', check=False).returncode:
            raise ValueError('Selected base lacks the automatic review policy; use the updated integration branch')
        revision = git(root, 'rev-parse', base + '^{commit}')
        directory = root / '.worktrees' / args.name
        git(root, 'worktree', 'add', '-b', rules['branch_prefix'] + args.name, str(directory), revision)
        print('Created task:', directory, 'baseline:', revision)
    elif args.action == 'finish':
        branch_gate(root, policy(root))
        if paths(root):
            raise ValueError('Index already contains changes; review explicitly with prepare, then commit')
        if any(Path(n).is_absolute() or '..' in Path(n).parts or n in {'.', ''} for n in args.files):
            raise ValueError('Supply explicit repository-relative task paths; never stage the whole repository')
        path_gate(args.files)
        for name in args.files:
            if name.endswith('/') and not (root / name).is_dir():
                raise ValueError('Unknown task directory: ' + name)
        git(root, 'add', '--', *args.files)
        prepare(root, args.review_note, args.allow_uninitialized, args.large_change_reason)
        verify(root)
        git(root, 'commit', '-m', args.message)
        # A failed push leaves the local commit and receipt intact.
        branch = git(root, 'symbolic-ref', '--short', 'HEAD')
        verify(root, committed=True)
        rules = policy(root)
        if git(root, 'remote', 'get-url', '--push', rules['remote']) != rules['remote_url']:
            raise ValueError('Workspace push remote changed; local commit preserved')
        git(root, 'push', '-u', rules['remote'], branch)
        print('Committed and synchronized:', git(root, 'rev-parse', '--short', 'HEAD'), branch)
    elif args.action == 'ci':
        if git(root, 'merge-base', '--is-ancestor', policy(root)['required_ancestor'], 'HEAD', check=False).returncode:
            raise ValueError('CI branch lacks the required integration baseline')
        static_review(root, paths(root, args.base), base=args.base, allow_uninitialized=True)
        run_check(root, ['bash', 'scripts/cloud-check.sh', '--allow-uninitialized'], [])
        if git(root, 'status', '--porcelain', '--untracked-files=normal'):
            raise ValueError('Checks changed the checkout; generated files must be committed')
        print('PASS: remote host review; GPU validation remains separate')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, SyntaxError) as error:
        print('REVIEW BLOCKED:', error, file=sys.stderr)
        sys.exit(1)
