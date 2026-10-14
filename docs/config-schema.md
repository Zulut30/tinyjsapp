# Editor assistance for tinyjs.json

The [JSON Schema](../schema/tinyjs.schema.json) describes the configuration
fields used by the CLI and runtime. It supplies field descriptions, completion,
and type checks in editors that support JSON Schema Draft 2020-12.

For a local checkout, VS Code can associate the schema without adding a field
to the application's config. Add this to your user settings, replacing the path
with your checkout's absolute path (use a `file:///C:/...` URI on Windows):

```json
{
  "json.schemas": [{
    "fileMatch": ["/tinyjs.json"],
    "url": "file:///absolute/path/to/tinyjsapp/schema/tinyjs.schema.json"
  }]
}
```

Other editors can associate the same local schema file with `tinyjs.json`.
The template does not add a remote `$schema` URL, so creating a project does
not depend on network access or on a particular schema having been published.

## Compatibility and scope

Root fields and partial `macos`, `windows`, and `linux` blocks share the same
definitions. tinyjs merges plain objects recursively; arrays and scalars in
the active platform block replace the root values. Environment signing settings
then take precedence. Unknown fields remain allowed, including nested extension
fields, to support future tinyjs releases and application tooling.

The schema checks documented field shapes; it does not reproduce every implicit
JavaScript coercion. Optional settings that accept `null` retain that option.
It deliberately imposes no version format, bundle ID format, path regex, or
required root `name`: a platform block can provide the name. A schema-valid
fragment is therefore not necessarily a runnable app. The CLI still checks the
resolved name, incompatible options (such as `mainWindow: false` with `url`),
file existence, path safety, native executable formats, and signing credentials.
Validation does not grant or audit API capabilities.

## Verification

Use a separate virtual environment for the test-only validator; tinyjs gains
no runtime dependency:

```sh
python3 -m venv /tmp/tinyjs-schema-check
/tmp/tinyjs-schema-check/bin/python -m pip install 'jsonschema==4.26.0'
/tmp/tinyjs-schema-check/bin/python test/config-schema/check.py
```

On Windows, use the environment's `Scripts/python.exe` instead of `bin/python`.
The check validates the schema itself, tracked `tinyjs.json` files, parseable
JSON examples in the README, platform overrides, extension fields, and invalid
nested field types. Annotated JSON snippets containing comments are skipped.
To also check a newly generated project's config, pass its filename:

```sh
/tmp/tinyjs-schema-check/bin/python test/config-schema/check.py /path/to/new-app/tinyjs.json
```
