# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Launch an existing production overlay with a process-local terminal gate."""
from __future__ import annotations

import argparse
import builtins
import os
import runpy
import subprocess
import sys
import sysconfig
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--production-root', type=Path, required=True)
    parser.add_argument('--mode', choices=('supervisor', 'generator'), default='supervisor')
    args, remaining = parser.parse_known_args()
    root = args.production_root.resolve()
    sys.path.insert(0, str(root))
    if args.mode == 'supervisor':
        cuda = Path(sysconfig.get_paths()['purelib']) / 'nvidia/cu13'
        if (cuda / 'lib').is_dir():
            os.environ['LD_LIBRARY_PATH'] = str(cuda / 'lib') + (':' + os.environ['LD_LIBRARY_PATH'] if os.environ.get('LD_LIBRARY_PATH') else '')
        if not os.environ.get('CUDA_HOME') and (cuda / 'bin/nvcc').is_file():
            os.environ['CUDA_HOME'] = str(cuda)
        paths = [str(Path(sys.executable).parent)]
        if os.environ.get('CUDA_HOME'):
            paths.append(os.environ['CUDA_HOME'] + '/bin')
        os.environ['PATH'] = ':'.join(paths + [os.environ.get('PATH', '')])
        # Same prior local acceptance and environment behavior as run-local.sh.
        os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
        original = subprocess.Popen

        def child(command, *a, **kw):
            command = list(command)
            script = str(root / 'generate.py')
            if script in command:
                index = command.index(script)
                command[index:index + 1] = [str(Path(__file__).resolve()), '--mode', 'generator', '--production-root', str(root)]
            return original(command, *a, **kw)

        subprocess.Popen = child
        sys.argv = [str(root / 'run_local.py'), *remaining]
        try:
            runpy.run_path(str(root / 'run_local.py'), run_name='__main__')
        finally:
            subprocess.Popen = original
    else:
        import compat
        from terminal_gate import guarded_source

        def compile_gate(source, filename, mode, *a, **kw):
            if filename == '<openarm-final-hold>':
                source = guarded_source(source)
                print('Benchmark terminal acceptance gate inserted before export', flush=True)
            return builtins.compile(source, filename, mode, *a, **kw)

        # compat compiles the in-memory generator before telemetry wraps it.
        # Shadow compile only in that module and at the exact integration boundary.
        compat.compile = compile_gate
        sys.argv = [str(root / 'generate.py'), *remaining]
        runpy.run_path(str(root / 'generate.py'), run_name='__main__')


if __name__ == '__main__':
    main()
