#!/usr/bin/env python3
import json
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
    import jsonschema  # type: ignore
except Exception:
    print("Missing Python deps: pyyaml and jsonschema. Install with: pip install pyyaml jsonschema", file=sys.stderr)
    sys.exit(1)

config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config/app-config.yaml")
schema_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("schemas/app-config.schema.json")

if not config_path.exists():
    print(f"Config not found: {config_path}", file=sys.stderr)
    sys.exit(1)
if not schema_path.exists():
    print(f"Schema not found: {schema_path}", file=sys.stderr)
    sys.exit(1)

with config_path.open("r", encoding="utf-8") as handle:
    config = yaml.safe_load(handle)

with schema_path.open("r", encoding="utf-8") as handle:
    schema = json.load(handle)

validator = jsonschema.Draft202012Validator(schema)
errors = sorted(validator.iter_errors(config), key=lambda e: list(e.path))

if errors:
    print(f"Config validation failed with {len(errors)} error(s):", file=sys.stderr)
    for error in errors:
        path = ".".join([str(p) for p in error.path]) or "<root>"
        print(f"- {path}: {error.message}", file=sys.stderr)
    sys.exit(1)

print("Config validation passed.")
