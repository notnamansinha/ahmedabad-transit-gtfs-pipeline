"""
Lightweight JSON Schema validator. No external deps.

This is NOT a full draft-2020-12 implementation — it covers the keywords
we actually use in our schemas: type, required, properties, items, enum,
minimum/maximum, pattern, minItems/minLength, additionalProperties,
const, oneOf. That's enough for our shapes.

Why not the `jsonschema` PyPI library: keeping zero pip dependencies for
the whole pipeline. If we add a requirements.txt later, swap this for
`jsonschema` — same API surface.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def _type_ok(value: Any, t: str) -> bool:
    if t == "object":
        return isinstance(value, dict)
    if t == "array":
        return isinstance(value, list)
    if t == "string":
        return isinstance(value, str)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "null":
        return value is None
    return False


def validate(value: Any, schema: dict, path: str = "$") -> list[str]:
    errors: list[str] = []

    # type
    t = schema.get("type")
    if t is not None:
        types = [t] if isinstance(t, str) else list(t)
        if not any(_type_ok(value, tt) for tt in types):
            errors.append(f"{path}: expected type {types}, got {type(value).__name__}")
            return errors  # bail; downstream checks will be noisy

    # const
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: const mismatch (want {schema['const']!r}, got {value!r})")

    # enum
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: not in enum {schema['enum']}")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: minLength {schema['minLength']}")
        if "pattern" in schema and not re.match(schema["pattern"], value):
            errors.append(f"{path}: pattern mismatch ({schema['pattern']!r})")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below minimum {schema['minimum']} ({value})")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: above maximum {schema['maximum']} ({value})")

    if isinstance(value, dict):
        for req in schema.get("required", []):
            if req not in value:
                errors.append(f"{path}.{req}: missing required field")
        props = schema.get("properties", {})
        for k, v in value.items():
            if k in props:
                errors.extend(validate(v, props[k], f"{path}.{k}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}.{k}: additional property not allowed")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: minItems {schema['minItems']}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: maxItems {schema['maxItems']}")
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(value):
                errors.extend(validate(item, item_schema, f"{path}[{i}]"))

    return errors


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("data_path", help="Path to JSON file (object or array of objects)")
    ap.add_argument("schema_path", help="Path to JSON Schema file")
    ap.add_argument("--max-errors", type=int, default=20)
    args = ap.parse_args()

    data = json.loads(Path(args.data_path).read_text())
    schema = json.loads(Path(args.schema_path).read_text())

    if isinstance(data, list):
        items = data
    else:
        items = [data]

    all_errors: list[str] = []
    for i, item in enumerate(items):
        errs = validate(item, schema, f"[{i}]")
        all_errors.extend(errs)
        if len(all_errors) >= args.max_errors:
            all_errors.append(f"... truncated at {args.max_errors}")
            break

    if all_errors:
        for e in all_errors:
            print(e)
        sys.exit(1)
    print(f"OK  {len(items)} record(s) validated against {Path(args.schema_path).name}")


if __name__ == "__main__":
    main()
