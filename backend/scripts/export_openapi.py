"""Export the OpenAPI schema to backend/openapi.json.

The committed schema is the API contract snapshot: the frontend generates
its TypeScript types from it, and CI regenerates both and fails on any
diff — so a backend change that alters the contract cannot merge without
the regenerated types (and the compiler errors they surface) coming along.

Run from backend/:  uv run python scripts/export_openapi.py
"""

import json
from pathlib import Path

from app.main import create_app


def main() -> None:
    schema = create_app().openapi()
    out = Path(__file__).resolve().parents[1] / "openapi.json"
    out.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"wrote {out} ({len(schema['paths'])} paths)")


if __name__ == "__main__":
    main()
