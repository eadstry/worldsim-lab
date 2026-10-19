"""Exercise review receipts and branch gates against isolated real Git repositories."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('workspace_review', SOURCE / 'review-workspace.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


class ReviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.git('init', '-q', '-b', 'codex/test')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.invalid')
        (self.root / 'scripts').mkdir()
        shutil.copy2(SOURCE / 'check-version-management.py', self.root / 'scripts/check-version-management.py')
        (self.root / 'upstream-lock.json').write_text('{}')
        (self.root / '.gitmodules').write_text('')
        self.git('add', '.')
        self.git('commit', '-qm', 'Baseline')
        self.base = self.git('rev-parse', 'HEAD')
        (self.root / 'config').mkdir()
        self.rules = {'required_ancestor': self.base, 'branch_prefix': 'codex/',
                      'protected_branches': ['main', 'release/*'], 'large_change_files': 100,
                      'remote': 'origin', 'remote_url': 'https://example.invalid/repo.git'}
        (self.root / 'config/version-policy.json').write_text(json.dumps(self.rules))
        self.git('add', 'config')
        self.git('commit', '-qm', 'Policy')
        (self.root / 'source.py').write_text('value = 1\n')
        self.git('add', 'source.py')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.STDOUT, text=True).strip()

    def prepare(self):
        with patch.object(review, 'run_check') as run:
            run.side_effect = lambda root, command, checks: checks.append({'command': command, 'status': 'passed'})
            review.prepare(self.root, 'Reviewed the task diff and failure paths')

    def test_valid_receipt_allows_exact_index_and_its_commit(self):
        self.prepare()
        review.verify(self.root)
        self.git('commit', '-qm', 'Task')
        review.verify(self.root, committed=True)

    def test_missing_receipt_blocks_submission(self):
        with self.assertRaisesRegex(ValueError, 'Missing review receipt'):
            review.verify(self.root)

    def test_new_staged_content_invalidates_review(self):
        self.prepare()
        (self.root / 'source.py').write_text('value = 2\n')
        self.git('add', 'source.py')
        with self.assertRaisesRegex(ValueError, 'stale'):
            review.verify(self.root)

    def test_unstaged_or_untracked_content_cannot_influence_checks(self):
        self.prepare()
        (self.root / 'untracked.py').write_text('value = 3\n')
        with self.assertRaisesRegex(ValueError, 'Untracked'):
            review.verify(self.root)
        (self.root / 'untracked.py').unlink()
        (self.root / 'source.py').write_text('value = 2\n')
        with self.assertRaisesRegex(ValueError, 'unstaged'):
            review.verify(self.root)

    def test_main_and_detached_head_are_blocked(self):
        self.git('branch', '-m', 'main')
        with self.assertRaisesRegex(ValueError, 'protected'):
            review.branch_gate(self.root, self.rules)
        self.git('checkout', '--detach', '-q')
        with self.assertRaisesRegex(ValueError, 'Detached'):
            review.branch_gate(self.root, self.rules)

    def test_old_baseline_is_blocked(self):
        rules = dict(self.rules, required_ancestor='f' * 40)
        with self.assertRaisesRegex(ValueError, 'Old task baseline'):
            review.branch_gate(self.root, rules)

    def test_failed_checks_do_not_leave_a_valid_receipt(self):
        self.prepare()
        with patch.object(review, 'run_check', side_effect=ValueError('Required check failed')):
            with self.assertRaisesRegex(ValueError, 'Required check failed'):
                review.prepare(self.root, 'Review again')
        self.assertFalse(review.receipt_path(self.root).exists())

    def test_checked_snapshot_cannot_change_during_validation(self):
        def change(root, command, checks):
            (root / 'source.py').write_text('value = 99\n')
            self.git('add', 'source.py')
        with patch.object(review, 'run_check', side_effect=change):
            with self.assertRaisesRegex(ValueError, 'changed during checks'):
                review.prepare(self.root, 'Review task')
        self.assertFalse(review.receipt_path(self.root).exists())

    def test_runtime_and_dependency_changes_are_blocked(self):
        for name in ['workspace-overlays/demo/.local/config.json', 'workspace-overlays/demo/runtime/asset.zip',
                     'runs/output.json', 'secret.pem', '.env', 'upstream-lock.json']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                review.path_gate([name])

    def test_push_must_target_reviewed_branch_and_workspace_remote(self):
        self.prepare()
        self.git('commit', '-qm', 'Task')
        head = self.git('rev-parse', 'HEAD')
        valid = f'refs/heads/codex/test {head} refs/heads/codex/test {review.ZERO}'
        review.push_gate(self.root, 'origin', self.rules['remote_url'], valid)
        for remote, url, line in [('other', self.rules['remote_url'], valid),
                                 ('origin', self.rules['remote_url'], valid.replace('refs/heads/codex/test', 'refs/heads/main')),
                                 ('origin', self.rules['remote_url'], valid.replace(review.ZERO, 'e' * 40))]:
            with self.subTest(line=line), self.assertRaises(ValueError):
                review.push_gate(self.root, remote, url, line)

    def test_shared_hooks_protect_parallel_worktrees_without_local_hook_files(self):
        self.prepare()
        review.install(self.root)
        self.git('commit', '-qm', 'Reviewed task')
        parallel = self.root.parent / (self.root.name + '-parallel')
        self.addCleanup(shutil.rmtree, parallel, True)
        self.git('worktree', 'add', '-qb', 'codex/parallel', str(parallel), 'HEAD')
        self.assertFalse((parallel / '.githooks/pre-commit').exists())
        (parallel / 'source.py').write_text('value = 2\n')
        subprocess.run(['git', '-C', str(parallel), 'add', 'source.py'], check=True)
        result = subprocess.run(['git', '-C', str(parallel), 'commit', '-qm', 'Unreviewed'],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Missing review receipt', result.stderr)

    def test_ci_checks_sealed_metadata_against_base_not_only_head(self):
        folder = self.root / 'outputs/example/v001'
        folder.mkdir(parents=True)
        (folder / 'report.md').write_text('first')
        import hashlib
        manifest = {'sealed_at': '2026-10-15', 'files': {'report.md': hashlib.sha256(b'first').hexdigest()}}
        (folder / 'manifest.json').write_text(json.dumps(manifest))
        self.git('add', '.')
        self.git('commit', '-qm', 'Seal')
        base = self.git('rev-parse', 'HEAD')
        (folder / 'report.md').write_text('changed')
        manifest['files']['report.md'] = hashlib.sha256(b'changed').hexdigest()
        (folder / 'manifest.json').write_text(json.dumps(manifest))
        self.git('add', 'outputs')
        self.git('commit', '-qm', 'Illegally reseal')
        with self.assertRaisesRegex(ValueError, 'sealed metadata changed'):
            review.static_review(self.root, review.paths(self.root, base), base=base)


if __name__ == '__main__':
    unittest.main()
