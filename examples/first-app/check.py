#!/usr/bin/env python3
"""Exercise the actual UI, RPC, store and relocated build after setup.sh/setup.ps1.

Requires the host's desktop session (or a virtual display on Linux).
Only a temporary copy and a fresh, unique test app id are used.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

EXAMPLE = Path(__file__).resolve().parent
TOOL = EXAMPLE.parents[1]
TJS = TOOL / 'bin' / ('tjs.exe' if os.name == 'nt' else 'tjs')
MAC = sys.platform == 'darwin'


def run(argv, cwd):
    result = subprocess.run([str(arg) for arg in argv], cwd=cwd, capture_output=True,
                            text=True, encoding='utf-8', timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


BACKEND_CHECK = '''
import { api } from './src/backend/main.js';
function assert(value, message) { if (!value) throw new Error(message); }
let memory = null;
let fail = false;
const app = { store: {
  async get() { return memory; },
  async set(_key, value) {
    memory = value; // Reproduce the runtime: memory changes even on failure.
    return !fail;
  },
} };
async function fails(method, params) {
  fail = true;
  let rejected = false;
  try { await api[method](params, app); }
  catch (error) { rejected = error.message.includes('Could not save'); }
  assert(rejected, method + ' must report a disk failure');
  fail = false;
}
assert((await api.listNotes({}, app)).length === 0, 'initially empty');
await fails('addNote', { text: 'one note' });
assert(memory.length === 1, 'failed set changed runtime memory');
assert((await api.listNotes({}, app)).length === 0, 'failed add leaves saved model empty');
let notes = await api.addNote({ text: 'one note' }, app);
assert(notes.length === 1 && memory.length === 1, 'retry adds exactly one note');
const id = notes[0].id;
await fails('updateNote', { id, text: 'edited note' });
assert(memory[0].text === 'edited note', 'failed edit changed runtime memory');
assert((await api.listNotes({}, app))[0].text === 'one note', 'failed edit keeps saved model');
notes = await api.updateNote({ id, text: 'edited note' }, app);
assert(notes.length === 1 && notes[0].text === 'edited note', 'retry edits exactly one note');
await fails('deleteNote', { id });
assert(memory.length === 0, 'failed delete changed runtime memory');
assert((await api.listNotes({}, app)).length === 1, 'failed delete keeps saved model');
notes = await api.deleteNote({ id }, app);
assert(notes.length === 0 && memory.length === 0, 'retry deletes the original note');
console.log('PASS backend write failure and retry: add, edit, delete');
'''


CHECK = r'''
(async () => {
  function assert(value, message) { if (!value) throw new Error(message); }
  async function ready() {
    const until = Date.now() + 10000;
    while (document.getElementById('controls').disabled && Date.now() < until) {
      await new Promise(resolve => setTimeout(resolve, 20));
    }
    assert(!document.getElementById('controls').disabled, 'UI timeout');
    assert(!document.getElementById('error').textContent, document.getElementById('error').textContent);
  }
  const $ = id => document.getElementById(id);
  const first = '  <img src=x onerror="window.unexpectedScript=true"> Привет 📝\nsecond line  ';
  const updated = first + '\nUpdated after restart.';
  async function submit(text) {
    $('text').value = text;
    $('editor').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
    await ready();
  }
  async function rejects(method, params) {
    let rejected = false;
    try { await tiny.api.call(method, params); } catch { rejected = true; }
    assert(rejected, method + ' should reject invalid input');
  }
  try {
    await ready();
    if (STAGE === 'create') {
      assert($('empty').hidden === false, 'initially empty');
      await submit('temporary note');
      $('notes').querySelector('button').click();
      await submit('edited note');
      assert($('notes').querySelector('p').textContent === 'edited note', 'UI edit');
      await submit(first);
      $('notes').querySelectorAll('button')[1].click();
      await ready();
      assert($('notes').children.length === 1, 'UI delete');
      await rejects('addNote', { text: '   ' });
      await rejects('addNote', { text: 'x'.repeat(2001) });
      await rejects('addNote', { text: 42 });
      await rejects('updateNote', { id: 'missing', text: 'valid' });
      await rejects('deleteNote', { id: 'missing' });
      await Promise.all(['concurrent a', 'concurrent b'].map(text => tiny.api.call('addNote', { text })));
      const all = await tiny.api.call('listNotes');
      assert(all.length === 3, 'concurrent writes preserve both notes');
      for (const note of all.filter(note => note.text !== first)) {
        await tiny.api.call('deleteNote', { id: note.id });
      }
      // A rejected mutation must not poison subsequent successful calls.
      $('text').value = '   ';
      $('editor').dispatchEvent(new Event('submit', { cancelable: true }));
      const until = Date.now() + 10000;
      while ($('controls').disabled && Date.now() < until) await new Promise(r => setTimeout(r, 20));
      assert($('error').textContent && $('text').value === '   ', 'UI error retains editor text');
    } else {
      const expected = STAGE === 'restart' ? first : updated;
      assert($('notes').children.length === 1, 'one note survived restart');
      assert($('notes').querySelector('p').textContent === expected, 'exact text survived restart');
      assert(!$('notes').querySelector('img') && !window.unexpectedScript, 'text did not become markup');
      if (STAGE === 'restart') {
        $('notes').querySelector('button').click();
        await submit(updated);
      } else {
        $('notes').querySelectorAll('button')[1].click();
        await ready();
        assert($('empty').hidden === false, 'built UI delete');
      }
    }
    const notes = await tiny.api.call('listNotes');
    const expected = STAGE === 'create' ? first : updated;
    assert(STAGE === 'built' ? notes.length === 0 : notes.length === 1 && notes[0].text === expected,
           'persisted backend result');
    await tiny.api.call('__checkResult', { ok: true, stage: STAGE });
  } catch (error) {
    await tiny.api.call('__checkResult', { ok: false, error: String(error.stack || error) });
  }
})();
'''


def check():
    assert TJS.is_file(), 'Run setup.sh / setup.ps1 first: missing ' + str(TJS)
    app_id = 'org.tinyjs.firstnotes.check.' + uuid.uuid4().hex
    if MAC:
        data = Path.home() / 'Library/Application Support' / app_id
    elif os.name == 'nt':
        data = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming')) / app_id
    else:
        data = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / app_id
    assert not data.exists(), 'Test id already exists; refusing to use it'
    try:
        with tempfile.TemporaryDirectory(prefix='tinyjs-first-notes-') as directory:
            base = Path(directory).resolve()
            project = base / 'project with spaces ü'
            shutil.copytree(EXAMPLE / 'src', project / 'src')
            config = json.loads((EXAMPLE / 'tinyjs.json').read_text(encoding='utf-8'))
            config['id'] = app_id
            (project / 'tinyjs.json').write_text(json.dumps(config), encoding='utf-8')
            report = base / 'report.json'
            backend = project / 'src/backend/main.js'
            with backend.open('a', encoding='utf-8') as out:
                out.write('\napi.__checkResult = async (result, app) => {\n'
                          '  await tjs.writeFile(' + json.dumps(str(report)) + ', '
                          'new TextEncoder().encode(JSON.stringify(result)));\n'
                          '  setTimeout(() => app.quit(), 150);\n'
                          '  return true;\n};\n')
            regression = project / 'check-backend.js'
            regression.write_text(BACKEND_CHECK)
            result = run([TJS, 'run', regression], project)
            print(result.stdout.strip(), flush=True)
            html = project / 'src/frontend/index.html'
            html.write_text(html.read_text(encoding='utf-8').replace('</head>', '<script src="check.js" defer></script></head>'), encoding='utf-8')

            def stage(name):
                (project / 'src/frontend/check.js').write_text('const STAGE = ' + json.dumps(name) + ';\n' + CHECK, encoding='utf-8')

            def launch(argv, cwd):
                report.unlink(missing_ok=True)
                log = base / 'run.log'
                with log.open('w', encoding='utf-8') as out:
                    proc = subprocess.Popen([str(arg) for arg in argv], cwd=cwd, stdout=out,
                                            stderr=out, start_new_session=os.name != 'nt')
                    try:
                        deadline = time.monotonic() + 35
                        while not report.exists() and time.monotonic() < deadline and proc.poll() is None:
                            time.sleep(.1)
                        assert report.exists(), log.read_text(encoding='utf-8')
                        result = json.loads(report.read_text(encoding='utf-8'))
                        assert result.get('ok'), result
                        print('PASS', result['stage'], flush=True)
                    finally:
                        if os.name == 'nt':
                            if proc.poll() is None:
                                subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                                               capture_output=True, timeout=15)
                        else:
                            try:
                                os.killpg(proc.pid, signal.SIGTERM)
                            except ProcessLookupError:
                                pass
                        proc.wait(timeout=10)

            stage('create')
            launch([TJS, 'run', TOOL / 'cli.js', 'dev'], project)
            assert len(json.loads((data / 'store.json').read_text(encoding='utf-8'))['notes']) == 1
            stage('restart')
            launch([TJS, 'run', TOOL / 'cli.js', 'dev'], project)
            stage('built')
            run([TJS, 'run', TOOL / 'cli.js', 'build'], project)
            moved = base / 'relocated distribution ü'
            shutil.move(project / 'dist', moved)
            if MAC:
                bundle = moved / 'First Notes.app'
                run(['codesign', '--verify', '--deep', '--strict', bundle], base)
                binary = bundle / 'Contents/MacOS/first-notes'
            else:
                binary = moved / ('first-notes.exe' if os.name == 'nt' else 'first-notes')
            launch([binary], base)
            assert json.loads((data / 'store.json').read_text(encoding='utf-8'))['notes'] == []
            print('PASS build, relocation, disk contents' + (', ad-hoc signature' if MAC else ''), flush=True)
    finally:
        # Never touch the example's normal app id or another test run's data.
        if data.exists():
            shutil.rmtree(data)


if __name__ == '__main__':
    check()
