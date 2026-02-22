#!/usr/bin/env python
"""Validate an AppConfig YAML file against the JSON schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema
import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate AppConfig against schema.")
    parser.add_argument("--config", required=True, help="Path to AppConfig YAML.")
    parser.add_argument("--schema", required=True, help="Path to schema JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    jsonschema.validate(instance=config, schema=schema)
    print(f"Validated {args.config} against {args.schema}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
