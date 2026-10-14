#!/usr/bin/env python3
"""Exercise the real CLI with an isolated release layout; no GUI or SDK needed."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

TOOL = Path(__file__).resolve().parents[2]
WIN = os.name == 'nt'
RUNTIME = 'tjs.exe' if WIN else 'tjs'
LAUNCHER = 'launcher-win.exe' if WIN else 'launcher-macos' if sys.platform == 'darwin' else 'launcher-linux'


def snapshot(root):
    return {str(p.relative_to(root)): (p.stat().st_mode, hashlib.sha256(p.read_bytes()).hexdigest())
            for p in root.rglob('*') if p.is_file()}


with tempfile.TemporaryDirectory(prefix='tinyjs doctor ') as tmp:
    root = Path(tmp).resolve()
    install = root / 'release with spaces'
    outside = root / 'unrelated cwd'
    outside.mkdir()
    (install / 'bin').mkdir(parents=True)
    (install / 'native').mkdir()
    shutil.copy2(TOOL / 'cli.js', install / 'cli.js')
    shutil.copytree(TOOL / 'runtime', install / 'runtime')
    shutil.copy2(TOOL / 'bin' / RUNTIME, install / 'bin' / RUNTIME)
    shutil.copy2(TOOL / 'native' / LAUNCHER, install / 'native' / LAUNCHER)
    (install / 'VERSION').write_text('0.56.0\n')
    if not WIN:
        shutil.copy2(TOOL / 'tinyjs', install / 'tinyjs')
    env = dict(os.environ, PATH='')
    env.pop('TINYJS_LAUNCHER', None)

    def cli(*args, status=0, extra_env=None, wrapper=False):
        before = snapshot(root)
        command = [install / 'tinyjs'] if wrapper else [install / 'bin' / RUNTIME, 'run', install / 'cli.js']
        # The POSIX wrapper needs dirname/readlink; the JS diagnostics need no commands.
        call_env = dict(env, **(extra_env or {}))
        if wrapper:
            call_env['PATH'] = os.environ.get('PATH', '')
        p = subprocess.run([str(a) for a in command + list(args)], cwd=outside, env=call_env,
                           capture_output=True, text=True, encoding='utf-8', timeout=10)
        assert p.returncode == status, (p.returncode, p.stdout, p.stderr)
        assert snapshot(root) == before, 'CLI changed fixture files'
        assert not p.stderr, p.stderr
        return p.stdout

    out = cli('doctor')
    assert 'tinyjs 0.56.0 (txiki.js ' in out and 'doctor: 0 error(s)' in out, out
    assert 'OK: Bundled launcher: ' + str(install).replace('\\', '/') in out.replace('\\', '/'), out
    assert 'does not verify binary architecture' in out, out
    cli('version')
    assert 'tinyjs doctor' in cli()
    cli('unknown-command', status=1)
    cli('doctor', '--unknown', status=1)
    if not WIN:
        cli('doctor', wrapper=True)

    launcher = install / 'native' / LAUNCHER
    saved = launcher.read_bytes()
    mode = launcher.stat().st_mode
    launcher.unlink()
    assert 'FAIL: Bundled launcher' in cli('doctor', status=1)
    launcher.mkdir()
    assert 'expected a non-empty regular file' in cli('doctor', status=1)
    launcher.rmdir()
    launcher.write_bytes(b'')
    assert 'expected a non-empty regular file' in cli('doctor', status=1)
    launcher.write_bytes(saved)
    launcher.chmod(mode)
    if not WIN:
        launcher.chmod(0o644)
        out = cli('doctor', status=1)
        assert 'chmod +x' in out, out
        launcher.chmod(mode)
    out = cli('doctor', status=1, extra_env={'TINYJS_LAUNCHER': str(root / 'missing override')})
    assert 'FAIL: Dev launcher override' in out and 'Correct or unset TINYJS_LAUNCHER' in out, out
    cli('doctor', extra_env={'TINYJS_LAUNCHER': str(launcher)})
    if not WIN:
        # A launcher that writes on execution must never be spawned by doctor.
        launcher.write_text('#!/bin/sh\necho launched > "' + str(outside / 'launched') + '"\nexit 77\n')
        launcher.chmod(0o755)
        cli('doctor')
    (install / 'VERSION').unlink()
    assert 'tinyjs dev (txiki.js ' in cli('doctor')
    (install / 'bin' / RUNTIME).rename(install / 'bin' / ('alternate-' + RUNTIME))
    # The running runtime works, but a missing distribution runtime blocks build/dev.
    before = snapshot(root)
    p = subprocess.run([str(install / 'bin' / ('alternate-' + RUNTIME)), 'run', str(install / 'cli.js'), 'doctor'],
                       cwd=outside, env=env, capture_output=True, text=True, encoding='utf-8', timeout=10)
    assert p.returncode == 1 and 'FAIL: Bundled runtime' in p.stdout, (p.stdout, p.stderr)
    assert snapshot(root) == before
print('doctor: all checks passed (real runtime, isolated release, unrelated cwd, read-only fixtures)')
