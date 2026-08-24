"""JSONL audit log. Must never cause an execution to fail."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

_lock = threading.Lock()


def log(path: str | None, **fields: Any) -> None:
    if not path:
        return
    record = {"ts": datetime.now(timezone.utc).isoformat(), **fields}
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False)
        with _lock:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    except Exception:
        # Auditing is best-effort: a write error must not break anything.
        pass
