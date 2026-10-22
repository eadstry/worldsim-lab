import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("openpi_download_serve", Path(__file__).with_name("serve.py"))
serve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serve)


class DownloadRoutingTests(unittest.TestCase):
    def test_only_urls_change_and_hashes_versions_sources_remain(self):
        raw = '''version = 1
[[package]]
name = "example"
version = "1.2.3"
source = { registry = "https://pypi.org/simple" }
wheels = [{url = "https://files.pythonhosted.org/packages/a/example.whl", hash = "sha256:1234", size = 99}]
'''
        changed, count = serve.rewrite_lock(raw)
        self.assertEqual(count, 1)
        self.assertEqual(changed.replace(serve.MIRROR, serve.ORIGINAL), raw)
        self.assertIn('hash = "sha256:1234"', changed)
        self.assertIn('registry = "https://pypi.org/simple"', changed)

    def test_unknown_lock_is_rejected(self):
        with self.assertRaises(ValueError):
            serve.rewrite_lock('version = 1\n')

    def test_wrong_source_commit_cannot_modify_context(self):
        with tempfile.TemporaryDirectory() as temp:
            context = Path(temp)
            lock = context / "uv.lock"
            lock.write_text("original")
            with patch.object(serve.subprocess, "check_output", return_value="unexpected\n"):
                with self.assertRaises(ValueError):
                    serve.patch_context(context, "expected", context)
            self.assertEqual(lock.read_text(), "original")

    def test_non_build_commands_pass_through_unchanged(self):
        with patch.dict(serve.os.environ, {"OPENPI_MIRROR_DOCKER": "/usr/bin/docker"}):
            with patch.object(serve.os, "execv") as execute:
                serve.docker_shim(["run", "--rm", "--gpus", "all", "image"])
            execute.assert_called_once_with("/usr/bin/docker", ["/usr/bin/docker", "run", "--rm", "--gpus", "all", "image"])


if __name__ == "__main__":
    unittest.main()
