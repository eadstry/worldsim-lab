import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from regression import check_manifest, claim_directory


class IsolationTests(unittest.TestCase):
    def test_existing_directory_is_never_reused_or_emptied(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'batch'
            claim_directory(root)
            evidence = root / 'partial'
            evidence.write_text('preserve')
            with self.assertRaises(FileExistsError):
                claim_directory(root)
            self.assertEqual(evidence.read_text(), 'preserve')

    def test_dependency_mutation_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source.py'
            source.write_text('before')
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({str(source): hashlib.sha256(source.read_bytes()).hexdigest()}))
            check_manifest(manifest)
            source.write_text('after')
            with self.assertRaisesRegex(ValueError, 'Frozen dependency'):
                check_manifest(manifest)


if __name__ == '__main__':
    unittest.main()
