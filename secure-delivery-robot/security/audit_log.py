"""
Append-only delivery record, one JSON object per line.

Every unlock, every rejection, every lockout gets written here. For a delivery
robot this is not optional garnish — "the package was released to someone"
needs a record of who, when, at what confidence, and on whose authority.

JSONL because it is append-only, survives a power cut mid-write (you lose at
most the last line), and reads back with two lines of pandas for your report.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List

from config import settings

log = logging.getLogger(__name__)


class AuditLog:
    def __init__(self, path: Path = None):
        self.path = path or settings.AUDIT_LOG
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: str, **fields: Any) -> Dict:
        entry = {
            "ts": time.time(),
            "iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "event": event,
            **fields,
        }
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except OSError:
            log.exception("Could not write audit entry")
        return entry

    # convenience wrappers so call sites are self-documenting
    def delivery_granted(self, recipient, confidence, destination, **kw):
        return self.record("DELIVERY_GRANTED", recipient=recipient,
                           confidence=round(confidence, 4),
                           destination=destination, **kw)

    def delivery_denied(self, reason, confidence=0.0, destination=None, **kw):
        return self.record("DELIVERY_DENIED", reason=reason,
                           confidence=round(confidence, 4),
                           destination=destination, **kw)

    def lockout(self, attempts, **kw):
        return self.record("LOCKOUT", attempts=attempts, **kw)

    def read_all(self) -> List[Dict]:
        if not self.path.exists():
            return []
        out = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue    # tolerate a torn final line
        return out
