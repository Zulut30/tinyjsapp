#!/usr/bin/env python3
"""Dependency-free runner fixtures; optionally build and launch the real tinyjs app."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from prepare import prepare
from run import archive_info, inventory, trial

ROOT = Path(__file__).resolve().parent


class RunnerChecks(unittest.TestCase):
    def launch(self, body, timeout=0.4):
        return trial([sys.executable, '-c', body], str(ROOT), timeout, 0.005)

    def test_ready_and_unique_nonce(self):
        code = """import os,json,time
with open(os.environ['TINYJS_BENCH_READY'],'w') as f:
    json.dump({'nonce':os.environ['TINYJS_BENCH_NONCE'],'checksum':499500},f)
time.sleep(10)
"""
        for _ in range(2):
            result = self.launch(code)
            self.assertEqual(result['status'], 'ready')
            self.assertGreater(result['ready_seconds'], 0)
            self.assertLess(result['ready_seconds'], 0.4)

    def test_stale_marker(self):
        result = self.launch("""import os,json,time
with open(os.environ['TINYJS_BENCH_READY'],'w') as f:
    json.dump({'nonce':'old-run','checksum':499500},f)
time.sleep(10)
""")
        self.assertEqual(result['status'], 'invalid_ready')
        self.assertIsNone(result['ready_seconds'])

    def test_timeout_and_premature_exit(self):
        self.assertEqual(self.launch('import time;time.sleep(10)')['status'], 'timeout')
        self.assertEqual(self.launch('raise SystemExit(3)')['status'], 'premature_exit')

    def test_missing_executable(self):
        with self.assertRaises(FileNotFoundError):
            trial(['/nonexistent/tinyjs-benchmark'], str(ROOT), 0.1, 0.005)

    def test_partial_marker_then_ready(self):
        result = self.launch("""import os,json,time
p=os.environ['TINYJS_BENCH_READY']
open(p,'w').write('{')
time.sleep(.03)
with open(p,'w') as f:
    json.dump({'nonce':os.environ['TINYJS_BENCH_NONCE'],'checksum':499500},f)
time.sleep(10)
""")
        self.assertEqual(result['status'], 'ready')

    def test_cleanup_descendant(self):
        # Descendant ignores TERM; it must receive the final group KILL.
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'heartbeat'
            child = """import signal,time,sys
from pathlib import Path
signal.signal(signal.SIGTERM, signal.SIG_IGN)
p = Path(sys.argv[1])
while True:
    p.write_text(str(time.time()))
    time.sleep(.01)
"""
            body = (f"import subprocess,sys,time; subprocess.Popen([sys.executable, '-c', "
                    f"{child!r}, {str(path)!r}]); time.sleep(10)")
            self.assertEqual(self.launch(body)['status'], 'timeout')
            before = path.read_text()
            import time
            time.sleep(0.08)
            self.assertEqual(path.read_text(), before)

    def test_unrelated_process_survives(self):
        unrelated = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(10)'])
        try:
            self.assertEqual(self.launch('import time;time.sleep(10)')['status'], 'timeout')
            self.assertIsNone(unrelated.poll())
        finally:
            unrelated.terminate()
            unrelated.wait(timeout=2)

    def test_prepare_from_another_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / 'app'
            command = [sys.executable, str(ROOT / 'prepare.py'), 'tinyjs', str(destination)]
            subprocess.run(command, cwd=temp, check=True, capture_output=True, timeout=5)
            self.assertEqual((destination / 'src/frontend/workload.js').read_bytes(),
                             (ROOT / 'workload/workload.js').read_bytes())
            result = subprocess.run(command, cwd=temp, capture_output=True, text=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('already exists', result.stderr)

    def test_prepare_refuses_checkout_destinations_before_copying(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            alias = Path(temp) / 'checkout-alias'
            alias.symlink_to(ROOT.parent, target_is_directory=True)
            candidates = [ROOT / 'adapters/tinyjs/never-copy-here',
                          ROOT / 'never-copy-here', ROOT.parent / 'never-copy-here',
                          alias / 'never-copy-here']
            for destination in candidates:
                with self.subTest(destination=destination), patch('prepare.shutil.copytree') as copy:
                    with self.assertRaisesRegex(ValueError, 'outside the checkout'):
                        prepare('tinyjs', destination)
                    copy.assert_not_called()

    def test_prepare_refuses_dangling_symlink_via_cli(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / 'dangling'
            target = Path(temp) / 'missing'
            destination.symlink_to(target, target_is_directory=True)
            result = subprocess.run([sys.executable, str(ROOT / 'prepare.py'), 'tinyjs',
                                     str(destination)], capture_output=True, text=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('already exists', result.stderr)
            self.assertTrue(destination.is_symlink())
            self.assertFalse(target.exists())

    def test_poll_cannot_extend_readiness_timeout(self):
        import time
        start = time.perf_counter()
        result = trial([sys.executable, '-c', 'import time; time.sleep(10)'],
                       str(ROOT), 0.05, 86400)
        self.assertEqual(result['status'], 'timeout')
        self.assertLess(time.perf_counter() - start, 0.75)

    def test_sizes_hashes_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'app'
            root.mkdir()
            (root / 'file').write_bytes(b'12345')
            (root / 'link').symlink_to('file')
            first = inventory(root)
            self.assertEqual(first['apparent_bytes'], 9)
            (root / 'file').write_bytes(b'54321')
            self.assertNotEqual(first['tree_sha256'], inventory(root)['tree_sha256'])
            (root / 'bad').symlink_to('../outside')
            os.mkfifo(Path(temp) / 'fifo')
            with self.assertRaisesRegex(ValueError, 'regular'):
                inventory(Path(temp) / 'fifo')
            import hashlib
            self.assertEqual(archive_info(root / 'file')['sha256'],
                             hashlib.sha256(b'54321').hexdigest())
            with self.assertRaisesRegex(ValueError, 'escapes'):
                inventory(root)

    def test_manifest_metadata_unavailable_and_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / 'installed').mkdir()
            (base / 'installed' / 'binary').write_bytes(b'12345')
            (base / 'app.zip').write_bytes(b'zip')
            fixture = """import os,json,time
with open(os.environ['TINYJS_BENCH_READY'],'w') as f:
    json.dump({'nonce':os.environ['TINYJS_BENCH_NONCE'],'checksum':499500},f)
time.sleep(10)
"""
            manifest = {'tinyjs': {'argv': [sys.executable, '-c', fixture], 'cwd': '.',
                'versions': {'fixture': '1'}, 'build': 'fixture, no GUI',
                'installed': 'installed', 'archive': 'app.zip',
                'workload_tree_sha256': inventory(ROOT / 'workload')['tree_sha256']}}
            config = base / 'manifest.json'
            config.write_text(json.dumps(manifest))
            command = [sys.executable, str(ROOT / 'run.py'), str(config), '--runs', '2', '--timeout', '1']
            result = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            app = data['artifacts'][0]
            self.assertEqual(len(app['trials']), 3)
            self.assertEqual([t['phase'] for t in app['trials']], ['warmup', 'measured', 'measured'])
            self.assertEqual(app['installed']['apparent_bytes'], 5)
            self.assertEqual(app['archive']['bytes'], 3)
            self.assertEqual(data['artifacts'][1]['status'], 'unavailable')
            self.assertEqual(data['method']['memory']['status'], 'unsupported')
            self.assertTrue(data['host']['cpu'])
            manifest['tinyjs']['argv'] = [sys.executable, '-c', 'raise SystemExit(2)']
            config.write_text(json.dumps(manifest))
            result = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)['artifacts'][0]['status'], 'failed')


def smoke():
    with tempfile.TemporaryDirectory(prefix='tinyjs-benchmark-smoke-') as temp:
        destination = Path(temp) / 'app'
        prepare('tinyjs', destination)
        subprocess.run([str(ROOT.parent / 'tinyjs'), 'build'], cwd=destination, check=True, timeout=180)
        if sys.platform == 'darwin':
            import plistlib
            bundle = next((destination / 'dist').glob('*.app'))
            with (bundle / 'Contents/Info.plist').open('rb') as stream:
                name = plistlib.load(stream)['CFBundleExecutable']
            # Direct bundle entry point preserves environment and process ownership.
            executable = bundle / 'Contents/MacOS' / name
        else:
            executable = destination / 'dist/startup-benchmark'
        import shutil
        installed = bundle if sys.platform == 'darwin' else destination / 'dist'
        archive = shutil.make_archive(str(Path(temp) / 'distribution'), 'zip',
                                      root_dir=installed.parent, base_dir=installed.name)
        versions = subprocess.check_output([str(ROOT.parent / 'tinyjs'), '--version'], text=True).strip()
        config = Path(temp) / 'manifest.json'
        config.write_text(json.dumps({'tinyjs': {
            'argv': [str(executable)], 'cwd': str(executable.parent),
            'installed': str(installed), 'archive': archive,
            'workload_tree_sha256': inventory(ROOT / 'workload')['tree_sha256'],
            'versions': {'tinyjs': versions}, 'build': str(ROOT.parent / 'tinyjs') + ' build'
        }}))
        result = subprocess.run([sys.executable, str(ROOT / 'run.py'), str(config),
                                 '--runs', '2', '--warmups', '1'],
                                capture_output=True, text=True, timeout=90)
        print(result.stdout)
        if result.returncode:
            raise SystemExit('real tinyjs runner smoke failed: ' + result.stderr)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tinyjs-smoke', action='store_true')
    args = parser.parse_args()
    if os.name != 'posix':
        parser.error('fixtures require POSIX process groups')
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RunnerChecks))
    if not result.wasSuccessful():
        raise SystemExit(1)
    if args.tinyjs_smoke:
        smoke()
