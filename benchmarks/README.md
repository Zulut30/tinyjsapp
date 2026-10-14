# Desktop startup benchmark

This is a measurement tool, not a performance claim. It launches **supplied,
packaged artifacts**, runs one identical frontend workload, and emits JSON.
There are no comparative results in this directory. Python 3.9+ and a working
GUI session on macOS or Linux are required. Windows cleanup is unsupported;
process groups cannot safely substitute for Windows Job Objects.

## What is measured

Each fresh process receives a unique nonce and a private, initially absent
marker path through `TINYJS_BENCH_NONCE` and `TINYJS_BENCH_READY`. The shared page
requests 1,000 integers from its backend, creates 1,000 DOM rows, computes their
sum, forces layout, then calls the backend again with the nonce and checksum.
Only that backend call writes the marker. Startup is the monotonic duration
from immediately before `Popen` to observation of the valid marker. This
includes IPC, frontend loading, layout, and polling overhead (default 5 ms).
It is **not** a pixel presentation timestamp, compositor measurement, or spawn
latency. Apps stay open until the runner stops their own process group.

The first launch has an **uncontrolled OS cache**, not a cold cache. `--warmups 1`
runs and discards one launch before the default five measured launches. Every
trial starts a new process, but subsequent launches may benefit from filesystem,
WebView, extraction, and application caches. `--warmups 0 --runs 1` measures a
first observed fresh-process launch, still not a cold-cache launch. No caches
are dropped and no system settings are changed. App data is not reset between
trials. Record whether artifacts have run before, and retain all raw trials.

Archive size is the exact number of bytes in the supplied distribution archive,
with a conventional SHA-256 of its bytes. Installed size is **apparent file
bytes**, not allocated disk space: sum regular file sizes, count hardlinks per
path, and count internal symlinks by their link text without following them.
Directories contribute zero bytes. External symlinks and special files are
rejected. `tree_sha256` is an inventory fingerprint including relative names,
modes, entry types, lengths and file contents; it is not a standard file hash.
Use the complete `.app` or portable distribution directory, including its
runtime and resources. OS-provided WebKit/WebView libraries are excluded;
Electron's bundled Chromium is included. Do not compare a debug executable or
an unpackaged runtime against complete release bundles.

Memory is explicitly **unsupported**. macOS WebKit XPC processes can be owned by
launchd and shared/reparented. Summing root/descendant RSS would undercount them
and double-count shared pages elsewhere. No total-RAM ranking is produced.

## Prepare and build reference apps

Run these commands from the repository root. Choose new directories outside the
checkout; preparation refuses existing destinations. Each copies the exact
same `workload/` files, plus only the framework-specific IPC adapter. The Tauri
preparer also generates a small deterministic placeholder PNG required by its
compiler. The source adapters contain no dependency lockfiles: generate and
retain locks, exact tool versions and build commands with your local experiment.

```sh
python3 benchmarks/prepare.py tinyjs /tmp/bench-tinyjs
python3 benchmarks/prepare.py electron /tmp/bench-electron
python3 benchmarks/prepare.py tauri /tmp/bench-tauri
```

Build tinyjs using this checkout's absolute CLI path (substitute your path):

```sh
cd /tmp/bench-tinyjs
/path/to/tinyjsapp/tinyjs build
```

On macOS the installed artifact is `dist/Startup benchmark.app`. Invoke its
`Contents/MacOS/startup-benchmark` executable directly. `open`, shell background
launchers, and wrappers that detach or exit early lose process ownership and
are unsupported. On Linux use the complete `dist` folder and its
`startup-benchmark` executable.

For Electron, select exact versions supported on your OS, then package a release
application, **not** `electron .`. Replace `ELECTRON_VERSION` and
`PACKAGER_VERSION` with exact versions:

```sh
cd /tmp/bench-electron
npm install --save-dev --save-exact electron@ELECTRON_VERSION @electron/packager@PACKAGER_VERSION
./node_modules/.bin/electron-packager . StartupBenchmark --out out --prune=true
```

Use the `.app` on macOS, or the entire output platform folder on Linux. Retain
`package-lock.json`. Record `process.versions` from this Electron build (Electron,
Chromium and Node), the packager version, and build flags in the manifest.

For Tauri, install its [platform prerequisites](https://v2.tauri.app/start/prerequisites/).
The adapter targets Tauri 2 and custom commands; no additional plugin is needed.
Choose a Tauri CLI 2 version compatible with the resolved crate and retain
`Cargo.lock`. An initial compile creates the lock; subsequent builds use it:

```sh
cd /tmp/bench-tauri
cargo build --release
cargo build --release --locked
```

These commands produce an embedded-frontend release binary for adapter smoke
checks. For a distribution comparison, bundle it using Tauri CLI 2 and enable
bundling in `tauri.conf.json` (`bundle.active: true`), then use
`cargo tauri build --bundles app` on macOS or the appropriate Linux distribution
format. The runner accepts existing artifact paths and does not install or
build dependencies. Record exact `cargo tree --locked` versions (especially
`tauri`, `wry`, `tao`), `rustc -Vv`, CLI version and build commands. Default native
window decorations and framework security defaults are retained; this workload
is not representative of every desktop app.

## Manifest and running

All paths are resolved relative to the manifest file; `argv` is an argument
array passed directly to the OS, **never a shell command**. Its executable must
be absolute or resolvable in PATH; relative arguments are resolved from `cwd`.
Only supply artifacts built from the current shared workload. Compute its
fingerprint from the checkout (substitute the actual frontend build directory
to verify the prepared copy agrees):

```sh
python3 -c 'import sys; sys.path.insert(0,"benchmarks"); from run import inventory; print(inventory("benchmarks/workload")["tree_sha256"])'
```

Create your archive outside the installed tree, using the same compression
format and settings for all frameworks. For example, on macOS:

```sh
cd /tmp/bench-tinyjs/dist
ditto -c -k --keepParent 'Startup benchmark.app' /tmp/tinyjs-benchmark.zip
```

Save this as `/tmp/benchmark-manifest.json`, replace placeholders with real
values and add `electron` / `tauri` entries using the same fields when available:

```json
{
  "tinyjs": {
    "argv": ["/tmp/bench-tinyjs/dist/Startup benchmark.app/Contents/MacOS/startup-benchmark"],
    "cwd": "/tmp/bench-tinyjs/dist",
    "installed": "/tmp/bench-tinyjs/dist/Startup benchmark.app",
    "archive": "/tmp/tinyjs-benchmark.zip",
    "workload_tree_sha256": "COPY_THE_FINGERPRINT_HERE",
    "versions": {"tinyjs": "EXACT_TAG_AND_COMMIT", "txiki": "EXACT_VERSION", "webview": "OS_VERSION"},
    "build": "EXACT_BUILD_COMMANDS_FLAGS_AND_LOCKFILE_HASHES"
  }
}
```

```sh
python3 benchmarks/run.py /tmp/benchmark-manifest.json > /tmp/benchmark-results.json
```

Missing framework entries become `unavailable`, never fabricated measurements.
Malformed metadata produces an actionable error. A failed launch stops that
framework's remaining trials, records `timeout`, `invalid_ready` or
`premature_exit`, and exits nonzero after writing JSON. Failed trials never
receive a startup time. Captured process output is diagnostic; inspect it before
sharing. Cleanup sends TERM then KILL only to the new process group, with finite
waits. Adapters must not daemonize or escape that group. OS-owned XPC processes
are outside this cleanup contract and are never matched by name or killed.

The runner records OS, architecture, CPU, logical CPU count, Python version,
artifact hashes, workload fingerprint, declared framework versions, argv, build
commands and every raw trial. Version/build/workload declarations are supplied
by the operator, not independently proven by inspecting an arbitrary binary.
Keep source revisions, generated lockfiles and artifacts alongside the results.
A matching declaration cannot certify that a third-party binary is equivalent.
Run each framework separately in randomized order across multiple batches on
an otherwise idle machine; retain power/display/session conditions and OS
WebView versions with those batches before drawing conclusions.

## Verification

```sh
python3 benchmarks/check.py
python3 benchmarks/check.py --tinyjs-smoke
python3 benchmarks/run.py --help
```

Fixtures exercise readiness, stale nonces, partial writes, timeout, early exit,
repetition, metadata, unavailable frameworks, separate size/hash semantics,
symlink escape rejection and process-group descendant cleanup. The optional
smoke builds and launches a real tinyjs GUI app in a temporary directory; it
requires the checkout's `tjs` and native launcher. It prints a local diagnostic,
not a published comparison. Always smoke any newly built Electron/Tauri artifact
through the runner before comparing it. Do not commit results, artifacts,
`node_modules`, `target` or generated locks to this directory.

Adapter API references: [Electron IPC](https://www.electronjs.org/docs/latest/tutorial/ipc),
[Tauri Rust commands](https://v2.tauri.app/develop/calling-rust/),
[Tauri configuration](https://v2.tauri.app/reference/config/).
