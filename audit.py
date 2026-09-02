"""Append one JSON object per LLM call to debug.json. No user text."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DEBUG_LOG = Path(__file__).resolve().parent / "debug.json"


def _write(event: dict, log_path: Optional[Path] = None) -> None:
    path = log_path or DEBUG_LOG
    event["timestamp"] = datetime.now(timezone.utc).isoformat()
    event["log_safe"] = True
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")


def log_llm_usage(input_tokens: int, output_tokens: int, elapsed_ms: Optional[int] = None, log_path: Optional[Path] = None) -> None:
    event = {"event": "llm_call_completed", "input_tokens": input_tokens, "output_tokens": output_tokens}
    if elapsed_ms is not None:
        event["elapsed_ms"] = elapsed_ms
    _write(event, log_path)


def log_error(kind: str, attempt: int, log_path: Optional[Path] = None) -> None:
    _write({"event": "llm_error", "error_type": kind, "attempt": attempt}, log_path)
