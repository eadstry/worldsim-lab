"""Exercise version guards against isolated real Git indexes and sealed artifacts."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('version_check', Path(__file__).resolve().parents[1] / 'check-version-management.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class VersionChecks(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.git('init', '-q')
        (self.root / 'upstream-lock.json').write_text('{}')
        (self.root / '.gitmodules').write_text('')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.STDOUT)

    def check(self):
        return checker.check(self.root, allow_uninitialized=True)[0]

    def seal(self):
        folder = self.root / 'outputs/example/v001'
        folder.mkdir(parents=True)
        (folder / 'report.md').write_text('sealed content')
        manifest = {'sealed_at': '2026-10-14', 'files': {'report.md': hashlib.sha256(b'sealed content').hexdigest()},
                    'delivery': {}}
        (folder / 'manifest.json').write_text(json.dumps(manifest))
        self.git('add', '.')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'Seal fixture')
        return folder, manifest

    def test_valid_sealed_version(self):
        self.seal()
        self.assertEqual(self.check(), [])

    def test_hook_index_does_not_leak_into_nested_checkout(self):
        child = self.root / 'child'
        self.git('init', '-q', '--separate-git-dir', str(self.root / 'child-git'), str(child))
        with patch.dict(os.environ, {'GIT_INDEX_FILE': '.git/index'}):
            result = checker.git(child, 'status', '--porcelain')
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_changed_payload_and_resealed_manifest_rejected(self):
        folder, manifest = self.seal()
        (folder / 'report.md').write_text('replaced content')
        self.assertTrue(any('sealed file' in x for x in self.check()))
        manifest['files']['report.md'] = hashlib.sha256(b'replaced content').hexdigest()
        (folder / 'manifest.json').write_text(json.dumps(manifest))
        self.assertTrue(any('sealed metadata changed' in x for x in self.check()))

    def test_deleted_version_rejected(self):
        folder, _ = self.seal()
        (folder / 'manifest.json').unlink()
        self.assertTrue(any('recorded version deleted' in x for x in self.check()))

    def test_delivery_receipt_update_allowed(self):
        folder, manifest = self.seal()
        manifest['delivery'] = {'local': {'status': 'verified'}}
        (folder / 'manifest.json').write_text(json.dumps(manifest))
        self.assertEqual(self.check(), [])

    def test_staged_deletion_cannot_hide_behind_worktree_copy(self):
        self.seal()
        self.git('rm', '--cached', 'outputs/example/v001/manifest.json')
        self.assertTrue(any('recorded version deleted' in x for x in self.check()))

    def test_sealed_payload_must_be_in_index(self):
        self.seal()
        self.git('rm', '--cached', 'outputs/example/v001/report.md')
        self.assertTrue(any('payload absent from Git index' in x for x in self.check()))

    def test_partially_staged_changes_rejected(self):
        path = self.root / 'source.py'
        path.write_text('reviewed')
        self.git('add', 'source.py')
        path.write_text('unreviewed')
        self.assertTrue(any('unstaged changes' in x for x in self.check()))

    def test_gitlink_lock_disagreement_rejected(self):
        sha = '1' * 40
        (self.root / '.gitmodules').write_text('[submodule "AutoData"]\n path = AutoData\n url = https://example.invalid/AutoData.git\n')
        (self.root / 'upstream-lock.json').write_text(json.dumps({'AutoData': {
            'commit': '2' * 40, 'url': 'https://example.invalid/AutoData.git'}}))
        self.git('update-index', '--add', '--cacheinfo', f'160000,{sha},AutoData')
        self.assertTrue(any('lock commit differs' in x for x in self.check()))

    def test_unstaged_lock_cannot_authorize_staged_gitlink(self):
        url = 'https://example.invalid/AutoData.git'
        (self.root / '.gitmodules').write_text('[submodule "AutoData"]\n path = AutoData\n url = ' + url + '\n')
        lock = self.root / 'upstream-lock.json'
        lock.write_text(json.dumps({'AutoData': {'commit': '1' * 40, 'url': url}}))
        self.git('add', '.gitmodules', 'upstream-lock.json')
        lock.write_text(json.dumps({'AutoData': {'commit': '2' * 40, 'url': url}}))
        self.git('update-index', '--add', '--cacheinfo', '160000,' + '2' * 40 + ',AutoData')
        self.assertTrue(any('metadata must be staged' in x for x in self.check()))

    def test_staged_dataset_and_secret_rejected(self):
        for name in ('dataset.hdf5', '.env'):
            (self.root / name).write_text('fixture')
        self.git('add', '.')
        self.assertEqual(sum('file staged' in x for x in self.check()), 2)


if __name__ == '__main__':
    unittest.main()
