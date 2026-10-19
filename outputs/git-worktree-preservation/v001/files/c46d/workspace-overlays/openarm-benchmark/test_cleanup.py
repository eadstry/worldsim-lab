# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Verify watchdog termination allows shared-memory cleanup without a GPU."""
import subprocess
import sys
import time
import unittest
from pathlib import Path

from bench32 import terminate


class CleanupTests(unittest.TestCase):
    def test_queue_memory_is_unlinked_after_termination(self):
        child = subprocess.Popen([sys.executable, '-c',
                                  'from multiprocessing.shared_memory import SharedMemory; import time; '
                                  'memory=SharedMemory(create=True,size=1024); print(memory.name,flush=True); time.sleep(30)'],
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        name = child.stdout.readline().strip()
        self.assertTrue(name)
        segment = Path('/dev/shm') / name
        self.assertTrue(segment.exists())
        terminate(child)
        deadline = time.monotonic() + 3
        while segment.exists() and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertFalse(segment.exists(), 'Watchdog left an export shared-memory segment')
        child.stdout.close()


if __name__ == '__main__':
    unittest.main()
