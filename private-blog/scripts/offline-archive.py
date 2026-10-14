#!/usr/bin/env python3
"""Build a deterministic offline ZIP or verify its CRCs with the standard library."""
import argparse
from pathlib import Path
import tempfile
import zipfile


def build(source, destination):
    # Stable order, timestamps and permissions avoid ZIP-only Git diffs on rebuild.
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        output = Path(temporary) / 'offline.zip'
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(source.rglob('*')):
                if not path.is_file():
                    continue
                entry = zipfile.ZipInfo(path.relative_to(source).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, path.read_bytes(), compresslevel=9)
        output.replace(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'check'])
    parser.add_argument('path', type=Path)
    parser.add_argument('destination', type=Path, nargs='?')
    args = parser.parse_args()
    if args.action == 'build':
        if args.destination is None:
            parser.error('build requires a destination')
        build(args.path, args.destination)
    else:
        with zipfile.ZipFile(args.path) as archive:
            failed = archive.testzip()
            if failed:
                raise ValueError(f'ZIP CRC check failed: {failed}')


if __name__ == '__main__':
    main()
