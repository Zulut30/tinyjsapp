#!/usr/bin/env python3
"""Copy a reference app to a NEW directory outside the checkout."""
import argparse
from pathlib import Path
import shutil
import struct
import zlib


def prepare(framework, destination):
    source = Path(__file__).resolve().parent
    if destination.exists():
        raise ValueError(f"destination already exists: {destination}")
    shutil.copytree(source / 'adapters' / framework, destination)
    frontend = destination / ('src/frontend' if framework == 'tinyjs' else 'frontend')
    shutil.copytree(source / 'workload', frontend)
    if framework == 'tauri':
        # Tauri requires a PNG icon at compile time, even without bundling.
        def chunk(kind, data):
            return (struct.pack('!I', len(data)) + kind + data
                    + struct.pack('!I', zlib.crc32(kind + data)))
        png = b'\x89PNG\r\n\x1a\n'
        png += chunk(b'IHDR', struct.pack('!2I5B', 32, 32, 8, 6, 0, 0, 0))
        png += chunk(b'IDAT', zlib.compress((b'\0' + b'\x30\x60\x90\xff' * 32) * 32))
        png += chunk(b'IEND', b'')
        (destination / 'icons').mkdir()
        (destination / 'icons/icon.png').write_bytes(png)
    if framework == 'tinyjs':
        backend = destination / 'src/backend'
        backend.mkdir(parents=True)
        (destination / 'main.js').rename(backend / 'main.js')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('framework', choices=['tinyjs', 'electron', 'tauri'])
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    try:
        prepare(args.framework, args.destination.resolve())
    except (OSError, ValueError) as error:
        parser.error(str(error))
