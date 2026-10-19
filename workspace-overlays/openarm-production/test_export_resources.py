# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Host-only regression checks for export shared-memory capacity handling."""
import contextlib
import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from export_resources import GIB, SHM_RESERVE, check_export_capacity, resolve_export_memory_gib


class ExportCapacityTests(unittest.TestCase):
    def capacity(self, free):
        return patch('export_resources.shutil.disk_usage', return_value=SimpleNamespace(free=free))

    def test_rounded_48g_mount_reduces_48g_request(self):
        with self.capacity(50506452992), contextlib.redirect_stderr(io.StringIO()) as warning:
            self.assertEqual(resolve_export_memory_gib(48), 16)
            self.assertIn('47.038 GiB', warning.getvalue())
            check_export_capacity(16 * GIB)

    def test_fitting_budget_is_unchanged_and_quiet(self):
        with self.capacity(16 * GIB + SHM_RESERVE), contextlib.redirect_stderr(io.StringIO()) as warning:
            self.assertEqual(resolve_export_memory_gib(16), 16)
            check_export_capacity(16 * GIB)
            self.assertEqual(warning.getvalue(), '')

    def test_small_mount_keeps_reserve(self):
        with self.capacity(2 * GIB), contextlib.redirect_stderr(io.StringIO()):
            effective = resolve_export_memory_gib(48)
            self.assertEqual(int(effective * GIB), 2 * GIB - SHM_RESERVE)
            check_export_capacity(int(effective * GIB))

    def test_no_usable_capacity_fails_before_startup(self):
        with self.capacity(SHM_RESERVE):
            with self.assertRaisesRegex(RuntimeError, 'available 0.008 GiB'):
                resolve_export_memory_gib(48)

    def test_capacity_change_is_reported_with_values(self):
        with self.capacity(15 * GIB):
            with self.assertRaisesRegex(RuntimeError, 'budget 16.000 GiB.*available 15.000 GiB'):
                check_export_capacity(16 * GIB)


if __name__ == '__main__':
    unittest.main()
