#!/usr/bin/env python3
"""Artifact-based GUI startup benchmark. Python 3.9+, POSIX only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import signal
import stat
import subprocess
import tempfile
import time
import uuid

EXPECTED = 499500


def inventory(path):
    """Apparent file bytes; internal symlinks counted as link text, never followed."""
    root = Path(path).absolute()
    if not root.exists() or root.is_symlink():
        raise ValueError(f"artifact must exist and its root cannot be a symlink: {root}")
    if not root.is_file() and not root.is_dir():
        raise ValueError(f'artifact must be a regular file or directory: {root}')
    root = root.resolve()
    digest = hashlib.sha256()
    size = 0
    paths = [root] if root.is_file() else sorted(root.rglob('*'))
    for entry in paths:
        info = entry.lstat()
        name = entry.relative_to(root).as_posix() if entry != root else '.'
        digest.update(json.dumps([name, stat.S_IMODE(info.st_mode)]).encode() + b'\0')
        if entry.is_symlink():
            target = os.readlink(entry)
            if not entry.resolve().is_relative_to(root):
                raise ValueError(f"symlink escapes installed artifact: {entry}")
            data = os.fsencode(target)
            size += len(data)
            digest.update(b'L' + data + b'\0')
        elif entry.is_file():
            size += info.st_size
            digest.update(b'F' + str(info.st_size).encode() + b'\0')
            with entry.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
        elif entry.is_dir():
            digest.update(b'D\0')
        else:
            raise ValueError(f"unsupported artifact entry: {entry}")
    return {'path': str(root), 'apparent_bytes': size, 'tree_sha256': digest.hexdigest()}


def archive_info(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'archive must be a regular file, not a symlink: {path}')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return {'path': str(path.resolve()), 'bytes': path.stat().st_size, 'sha256': digest.hexdigest()}


def stop(process):
    # Every launch owns a new session/process group. Never match executable names.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    # Descendants can outlive their parent; always finish cleaning the group.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=2)


def trial(argv, cwd, timeout, interval):
    with tempfile.TemporaryDirectory(prefix='tinyjs-benchmark-') as temp:
        marker = Path(temp) / 'ready.json'
        nonce = uuid.uuid4().hex
        env = dict(os.environ, TINYJS_BENCH_NONCE=nonce, TINYJS_BENCH_READY=str(marker))
        with open(Path(temp) / 'output', 'w+b') as output:
            start = time.perf_counter()
            process = subprocess.Popen(argv, cwd=cwd, env=env, start_new_session=True,
                                       stdin=subprocess.DEVNULL, stdout=output, stderr=output)
            status, elapsed = 'timeout', None
            try:
                while time.perf_counter() - start < timeout:
                    if process.poll() is not None:
                        status = 'premature_exit'
                        break
                    if marker.exists():
                        try:
                            ready = json.loads(marker.read_text())
                        except (ValueError, OSError):
                            ready = None  # Ignore an incomplete JSON write until the next poll.
                        if ready is not None:
                            if ready != {'nonce': nonce, 'checksum': EXPECTED}:
                                status = 'invalid_ready'
                            else:
                                status, elapsed = 'ready', time.perf_counter() - start
                            break
                    time.sleep(interval)
            finally:
                stop(process)
            output.seek(0, os.SEEK_END)
            output.seek(max(0, output.tell() - 4096))
            return {'status': status, 'ready_seconds': elapsed,
                    'output_tail': output.read().decode(errors='replace')}


def positive(value):
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError('must be finite and positive')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path, help='artifact manifest; paths relative to this file')
    parser.add_argument('--runs', type=int, default=5)
    parser.add_argument('--warmups', type=int, default=1)
    parser.add_argument('--timeout', type=positive, default=20)
    parser.add_argument('--poll', type=positive, default=0.005)
    args = parser.parse_args()
    if os.name != 'posix':
        parser.error('unsupported: process cleanup requires POSIX process groups')
    if args.runs < 1 or args.warmups < 0:
        parser.error('runs must be >= 1 and warmups >= 0')
    try:
        manifest = json.loads(args.manifest.read_text())
        if not isinstance(manifest, dict):
            raise ValueError('manifest must be a JSON object keyed by framework')
        base = args.manifest.resolve().parent
        workload = inventory(Path(__file__).parent / 'workload')
        records = []
        for name in ('tinyjs', 'electron', 'tauri'):
            spec = manifest.get(name)
            if spec is None:
                records.append({'framework': name, 'status': 'unavailable',
                                'reason': 'no supplied artifact'})
                continue
            required = {'argv', 'cwd', 'installed', 'archive', 'versions', 'build', 'workload_tree_sha256'}
            if not isinstance(spec, dict) or not required.issubset(spec):
                raise ValueError(f'{name}: expected fields {sorted(required)}')
            if spec['workload_tree_sha256'] != workload['tree_sha256']:
                raise ValueError(f'{name}: declared workload fingerprint differs from reference')
            if not isinstance(spec['argv'], list) or not spec['argv'] or not all(
                    isinstance(arg, str) and arg for arg in spec['argv']):
                raise ValueError(f'{name}: argv must be a nonempty string array (no shell)')
            if not isinstance(spec['versions'], dict) or not spec['versions']:
                raise ValueError(f'{name}: record exact framework/runtime versions')
            cwd = (base / spec['cwd']).resolve()
            installed = inventory(base / spec['installed'])
            archive = base / spec['archive']
            record = {'framework': name, 'versions': spec['versions'], 'argv': spec['argv'],
                      'cwd': str(cwd), 'build': spec['build'], 'installed': installed,
                      'archive': archive_info(archive), 'trials': []}
            if not isinstance(spec['build'], str) or not spec['build'].strip():
                raise ValueError(f'{name}: record build commands and flags')
            for index in range(args.runs + args.warmups):
                result = trial(spec['argv'], cwd, args.timeout, args.poll)
                result['phase'] = 'warmup' if index < args.warmups else 'measured'
                record['trials'].append(result)
                if result['status'] != 'ready':
                    break
            record['status'] = ('ok' if all(t['status'] == 'ready' for t in record['trials'])
                                else 'failed')
            records.append(record)
        cpu = platform.processor()
        if platform.system() == 'Darwin':
            cpu = subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string'],
                                          text=True, timeout=2).strip()
        elif platform.system() == 'Linux':
            for line in Path('/proc/cpuinfo').read_text().splitlines():
                if line.startswith(('model name', 'Hardware')):
                    cpu = line.split(':', 1)[-1].strip()
                    break
        result = {
            'schema': 1, 'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
            'host': {'os': platform.platform(), 'machine': platform.machine(),
                     'cpu': cpu or 'unavailable', 'logical_cpus': os.cpu_count(),
                     'python': platform.python_version()},
            'workload': workload,
            'method': {
                'clock': 'perf_counter',
                'readiness': 'backend marker after frontend RPC and DOM work',
                'poll_seconds': args.poll, 'timeout_seconds': args.timeout,
                'runs': args.runs, 'warmups': args.warmups,
                'cache': 'uncontrolled OS cache',
                'size': ('apparent file bytes plus internal symlink text; '
                         'no directory bytes; hardlinks counted per path'),
                'memory': {'status': 'unsupported',
                           'reason': 'shared/reparented WebView processes cannot be attributed fairly'},
            },
            'artifacts': records,
        }
        print(json.dumps(result, indent=2))
        return int(any(record['status'] == 'failed' for record in records))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    raise SystemExit(main())
