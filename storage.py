"""Save a confirmed intake record. No user messages."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from models import IntakeRecord

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def save_intake_record(record: IntakeRecord, turns_taken: int, output_dir: Optional[Path] = None) -> Path:
    folder = Path(output_dir) if output_dir else OUTPUT_DIR
    folder.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    payload = {
        "query_type": record.query_type,
        "regulation_ref": record.regulation_ref,
        "product_area": record.product_area,
        "urgency": record.urgency,
        "submitting_team": record.submitting_team,
        "timestamp": now.isoformat(),
        "turns_taken": turns_taken,
        "log_safe": True,
    }
    path = folder / f"intake_{now.strftime('%Y%m%dT%H%M%S%f')}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
