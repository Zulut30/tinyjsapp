# Your first tinyjs app: a persistent notebook

Build a small desktop notebook with a plain HTML frontend, backend RPC and
local persistence. No framework, npm install or external service is needed.
The companion source is in [`examples/first-app`](../examples/first-app).
The broader example collection lives in
[`tinyjsapp-examples`](https://github.com/tarwin/tinyjsapp-examples); this
small example stays beside the tutorial so the steps and source can be read together.

## Run the notebook

Install tinyjs using the [setup instructions](../README.md#install), then
copy `examples/first-app` from this repository to a writable folder. From
that folder:

```sh
tinyjs dev
```

The window starts with an empty list. Add a note, edit it and save the changes.
Close the app, run `tinyjs dev` again and check that the note is still there.
Delete removes that note from the saved list immediately.

For a checkout of this repository, the equivalent commands are:

```sh
cd examples/first-app
../../tinyjs dev
```

On Windows, use `..\..\tinyjs.cmd dev`. Finish `setup.sh` or `setup.ps1`
first if the checkout does not yet have its runtime and launcher.

The project contains:

```text
tinyjs.json                 app name, window size, stable id and version
src/backend/main.js         the note API and storage operations
src/frontend/index.html     the form, status and saved-note list
src/frontend/app.js         form events, RPC calls and rendering
src/frontend/style.css      a small stylesheet
check.py                    optional integration check for a tinyjs checkout
```

Edit the frontend while `dev` is running to reload the page. Backend edits
restart the process. Unsaved editor text is not persistent, so save it before
editing source or closing the window.

## Follow a note from the page to the backend

The launcher injects the `tiny` global; no client library script is needed.
Submitting the form in `src/frontend/app.js` sends a JSON-compatible object:

```js
const notes = await tiny.api.call('addNote', { text: 'My first note' });
```

This calls the `addNote` function exported in the backend's `api` object.
Every handler receives `(params, app)`. The example validates that `text`
is a nonblank string with at most 2000 characters, reads the existing list,
adds a note with an id and saves the new list. The returned array crosses
the bridge back to the page, which renders it.

`listNotes`, `updateNote` and `deleteNote` follow the same path. Updates and
deletes use the saved id rather than the note's text, so two notes with the
same text remain independent. Backend mutations run in order to avoid
losing a note when two calls overlap.

The backend runs on **txiki.js**, not a full Node.js environment. This example
uses tinyjs's `app.store` rather than Node's `fs` module. Plain JavaScript
here needs no package manager. Other projects can use the TypeScript/bundling
workflow described in the [main guide](../README.md#create-and-run-an-app).

The page treats a note as user input: it assigns `textContent` to a created
element instead of inserting HTML. Try saving `<b>hello</b>`; it should appear
literally. RPC failures appear above the list, and a failed save keeps the
editor text so you can copy it or retry. Controls pause while a call is pending.

## Understand where the data goes

The backend stores its array under the `notes` key:

```js
const notes = await app.store.get('notes'); // null when not set
const saved = await app.store.set('notes', nextNotes);
if (!saved) throw new Error('Could not save notes to disk.');
```

The store writes JSON using a temporary file and rename. **Check the boolean
result:** a write failure resolves `false`; it does not reject the promise.
Its in-memory value can already have changed when a write fails, so the error
does not mean the runtime restored its previous value. The example compensates
by keeping the last successfully saved array in the backend and advancing it
only after `store.set` returns `true`. Retrying a failed add therefore creates
one note; failed edits and deletes do not change that model. Keep the editor
text and resolve the disk problem before relying on persistence.

The file is `store.json` in the directory selected by the app's `id`:

| Platform | Data directory for this example |
| --- | --- |
| macOS | `~/Library/Application Support/com.example.tinyjs.firstnotes/` |
| Windows | `%APPDATA%\com.example.tinyjs.firstnotes\` |
| Linux | `$XDG_DATA_HOME/com.example.tinyjs.firstnotes/`, falling back to `~/.local/share/com.example.tinyjs.firstnotes/` |

The backend can read the actual directory from `app.paths.data`; the frontend
can use `await tiny.app.paths()`. It is independent of the working directory
and the source folder. Development and built copies with the **same id share
data**. Choose your own stable id before using this as the basis for another
app. Changing it selects another data directory; it does not migrate notes.

This is a learning example for small, nonsensitive notes, not an encrypted
notebook or a backup system. Keep a backup of `store.json` before changing
its format. The runtime treats an unreadable or invalid JSON store as empty;
the example's array validation cannot detect that earlier read failure.
Do not treat an unexpectedly empty list as proof that no data existed.
Independent simultaneously running app processes are not a database with
transactions; use a database if your application needs that model.

## Build and try the distribution

Quit the development app, then run from the notebook folder:

```sh
tinyjs build
```

In a repository checkout use `../../tinyjs build` (Windows:
`..\..\tinyjs.cmd build`). Build for each target OS on that OS.

On macOS, try `dist/First Notes.app`. Copy that whole bundle to another
folder and open it there. On Linux or Windows, copy the **whole `dist/`
folder** and launch `first-notes` or `first-notes.exe` inside it. The portable
executable depends on its sibling files; copying only the executable is not
enough. The saved notes remain in the per-user data directory, so they are
not included when you send someone the build.

A local macOS build is signed ad hoc by default. That is useful for testing;
it is not Developer ID signing or notarization for public distribution.
Before sharing a release, follow the main guide's
[signing and notarization instructions](../README.md#distributing-to-other-people-developer-id--notarization).
Windows recipients may also see unsigned-application warnings; this tutorial
does not supply a trusted publisher certificate. Linux needs the system
libraries listed in the [main guide](../README.md).

## Check the example as a contributor

From the root of a tinyjs checkout with its runtime and launcher installed:

```sh
python3 -u examples/first-app/check.py
```

Use `python` instead of `python3` if that is your Python 3 command on Windows.
The check needs a desktop session (or a virtual display on Linux), Python 3.9+
and the normal host build tools. It first calls the exported backend with a
test store that updates memory but reports a failed write, checking successful
retries of add, edit and delete. It then drives the real HTML form and bridge,
checks invalid input and overlapping RPC calls, restarts the app to verify
exact text persistence, then builds and runs a relocated distribution. On
macOS it also verifies the bundle's ad-hoc signature with `codesign`.

It runs in a temporary source copy with a unique test app id, has finite
process timeouts and removes only that run's data directory. It does not
read or clear the notebook's normal saved notes. A passing run checks the
host OS only; it does not establish that the other platforms were tested.
