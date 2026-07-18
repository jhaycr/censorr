"""N2: structured JSON logs for the service and worker -- one JSON object
per line with stable fields (job_id, stage, event). The CLI keeps rich
human output; these logs are for `docker compose logs` and log shippers.
"""

import json
import sys
from datetime import UTC, datetime
from typing import Any


def log_event(event: str, **fields: Any) -> None:
    record = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "event": event,
        **{k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
           for k, v in fields.items()},
    }
    print(json.dumps(record, ensure_ascii=False), file=sys.stdout, flush=True)
