# Diagnose a tinyjs installation

Run `tinyjs doctor` from any directory. It needs no app project or compiler.
The command prints the tinyjs and txiki.js versions, platform and CPU model,
installation directory, running runtime path, and availability of the bundled
runtime and platform launcher. It also checks a `TINYJS_LAUNCHER` dev override
when set; packaged builds still require the bundled launcher.

Files must be non-empty regular files, with executable permission bits on
macOS/Linux. Missing or inaccessible paths and missing executable bits produce
`FAIL` messages with recovery instructions. Exit status is **1** for these
errors or unsupported arguments, **0** when the file checks pass. Notes and
warnings do not change that status.

`doctor` does not start subprocesses or windows, contact the network, install
anything, rebuild sources, or write files or update caches. It does not require
Xcode, a C++ compiler, Node.js, or package-manager tools for a release install.

## Limits

Passing file checks does not establish that an app can launch: binary
architecture, dynamic libraries, OS execution restrictions, GUI access, and
project configuration are not validated. The CPU line is the reported model,
not a check of the binary's architecture or translation mode.

macOS supplies WebKit. Linux reports that WebKitGTK/shared libraries are not
checked and shows runtime package instructions; a missing `DISPLAY` and
`WAYLAND_DISPLAY` also produces a desktop-session warning. Windows reports
that the WebView2 Runtime is not checked. Follow the platform installation
instructions in the [README](../README.md) if a window cannot open.

The wrapper needs `bin/tjs` (`bin/tjs.exe` on Windows) to run **any** command,
including `doctor`. If that runtime is missing, incompatible, or blocked by the
OS, the wrapper cannot start this diagnostic. Reinstall the release for your OS
and architecture, or run the source setup script as described in the README.
Missing `VERSION` in a source checkout is reported as `dev`.

## Verification

After installing/building the runtime and launcher, run:

```sh
python3 test/doctor/check.py
```

The test uses the actual CLI and runtime in temporary release layouts with
spaces in their paths. It checks successful and failed diagnostics from an
unrelated working directory and asserts that fixture contents and modes remain
unchanged. It does not open a window.
