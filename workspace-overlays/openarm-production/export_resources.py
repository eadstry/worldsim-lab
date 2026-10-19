# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Host-only shared-memory preflight for asynchronous dataset export."""
import math
import shutil
import sys

GIB = 1024**3
SHM_RESERVE = 8 * 1024**2


def check_export_capacity(memory_bytes):
    available = shutil.disk_usage('/dev/shm').free
    if memory_bytes + SHM_RESERVE > available:
        raise RuntimeError(
            f'Insufficient /dev/shm capacity: export budget {memory_bytes / GIB:.3f} GiB '
            f'+ reserve {SHM_RESERVE / GIB:.3f} GiB; available {available / GIB:.3f} GiB. '
            'Lower --export-queue-memory-gib or free shared memory before retrying.')


def resolve_export_memory_gib(requested):
    """Keep fitting budgets; reduce oversized requests before loading Isaac Sim."""
    assert math.isfinite(requested) and requested > 0
    available = shutil.disk_usage('/dev/shm').free
    usable = available - SHM_RESERVE
    if int(requested * GIB) <= usable:
        return requested
    if usable <= 0:
        check_export_capacity(int(requested * GIB))
    effective = min(16 * GIB, usable) / GIB
    print(f'[OpenArm preflight] /dev/shm available {available / GIB:.3f} GiB; '
          f'export budget {requested:g} GiB exceeds capacity including the 8 MiB reserve. '
          f'Using --export-queue-memory-gib {effective:g}. '
          'Simulation recorder memory is separate from this budget.', file=sys.stderr, flush=True)
    return effective
