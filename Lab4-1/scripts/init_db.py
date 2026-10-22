"""Initialize the configured application database without clearing it."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from survey_app.config import Settings
from survey_app.db import SCHEMAS, create_client, initialize_schema


def main() -> int:
    try:
        settings = Settings.from_env()
        with create_client(settings) as client:
            client.admin.command("ping")
            initialize_schema(client[settings.database])
        print(json.dumps({"status": "PASS", "database": settings.database, "collections": sorted(SCHEMAS)}, ensure_ascii=False))
        return 0
    except Exception as exc:
        # Driver exceptions may carry connection details; log only the error class.
        print(json.dumps({"status": "FAIL", "error_type": type(exc).__name__}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
