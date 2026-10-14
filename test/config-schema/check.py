#!/usr/bin/env python3
"""Validate the schema and compatibility corpus: python3 test/config-schema/check.py.

Requires the test-only jsonschema package; see docs/config-schema.md.
Additional arguments are generated/project tinyjs.json files to validate.
"""
import json
from pathlib import Path
import re
import subprocess
import sys

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
schema = json.loads((ROOT / 'schema/tinyjs.schema.json').read_text(encoding='utf-8'))
Draft202012Validator.check_schema(schema)
validator = Draft202012Validator(schema)
checked = 0


def valid(label, value):
    global checked
    errors = list(validator.iter_errors(value))
    assert not errors, (label, [error.message for error in errors])
    checked += 1


def invalid(label, value):
    global checked
    assert not validator.is_valid(value), label
    checked += 1


# Read the actual checked-in configurations, including future templates/tests.
tracked = subprocess.check_output(
    ['git', 'ls-files', '-z', '--', '*tinyjs.json'], cwd=ROOT
).decode().split('\0')
for filename in filter(None, tracked):
    valid(filename, json.loads((ROOT / filename).read_text(encoding='utf-8')))

# README fragments need not be complete apps (name can come from an OS block).
readme_count = 0
for block in re.findall(r'```json\n(.*?)```', (ROOT / 'README.md').read_text(encoding='utf-8'), re.S):
    try:
        config = json.loads(block)
    except json.JSONDecodeError:
        continue  # Annotated JSON, with // comments, is documentation only.
    valid('README JSON example', config)
    readme_count += 1
assert readme_count, 'README JSON examples were not found'

for label, config in [
    ('minimal', {'name': 'minimal'}),
    ('legacy layout', {'name': 'legacy', 'backend': 'src/main.js', 'frontend': {'dir': 'src/frontend'}}),
    ('bundled frontend', {'backend': 'backend/main.ts', 'frontend': {
        'build': 'npm run build', 'dist': 'dist', 'dev': 'npm run dev',
        'devUrl': 'http://127.0.0.1:5173', 'reload': False}}),
    ('future extensions', {'name': 'future', 'plugin': {'enabled': True},
        'update': {'url': 'https://example.com/manifest.json', 'futureKey': {'format': 1}},
        'chrome': {'newFeature': True}, 'linux': {'extension': [1, 2]}}),
    ('nullable optional settings', {'name': 'clear', 'frontend': None, 'chrome': None,
        'update': None, 'permissions': None, 'notarize': None, 'fileExtensions': None,
        'api': None, 'readAccess': None, 'activation': None, 'macos': None}),
    ('chrome reset', {'chrome': {'windowControlsPos': False, 'vibrancy': False}}),
    ('api origin forms', {'api': {'preset': 'wrapper', 'enable': ['custom'], 'origins': {
        'file://*': 'all', 'https://app.example.com': ['notify', 'store.*'],
        'https://blocked.example.com': False, 'https://limited.example.com': {
            'disable': ['*'], 'enable': ['notify']}}}}),
    ('api allow/deny flags', {'api': True, 'windows': {'api': 'none'}}),
    ('disabled update checks', {'update': {'auto': False}}),
    ('sidecar entitlements', {'macos': {'executableEntitlements': {
        'helper': ['com.apple.security.cs.allow-jit']}}}),
]:
    valid(label, config)

for os_key in ['macos', 'windows', 'linux']:
    valid(os_key + ' partial overrides', {
        'chrome': {'frame': False, 'windowControlsPos': {'x': 12, 'y': 24}},
        'resources': ['common.dat'],
        os_key: {'name': 'platform-name', 'chrome': {'windowControlsPos': {'x': 18}},
                 'resources': [], 'frontend': {'reload': False}}})
    invalid(os_key + ' malformed nested override', {os_key: {'frontend': {'reload': 'false'}}})
    invalid(os_key + ' malformed block', {os_key: []})

for label, config in [
    ('non-object config', []),
    ('resources is not a list', {'resources': None}),
    ('resource is not a path', {'resources': [42]}),
    ('executables is not a list', {'executables': 'helper'}),
    ('entitlements is not a list', {'executableEntitlements': {'helper': True}}),
    ('helpBook is not a path', {'helpBook': {}}),
    ('invalid activation', {'activation': 'background'}),
    ('window flag is not a boolean', {'mainWindow': None}),
    ('malformed optional field', {'update': []}),
    ('malformed update URL', {'update': {'url': 23}}),
    ('malformed chrome controls', {'chrome': {'windowControls': {}}}),
    ('malformed chrome coordinate', {'chrome': {'windowControlsPos': {'y': '24'}}}),
    ('malformed permission description', {'permissions': {'camera': []}}),
    ('malformed capability list', {'api': {'enable': [False]}}),
    ('malformed origin gate', {'api': {'origins': {'https://example.com': 42}}}),
]:
    invalid(label, config)

for filename in sys.argv[1:]:
    valid(filename, json.loads(Path(filename).read_text(encoding='utf-8')))

print(f'PASS schema meta-validation and {checked} configurations ({readme_count} README examples)')
