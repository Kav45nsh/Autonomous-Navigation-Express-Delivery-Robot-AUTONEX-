"""
FUTURE SCOPE STUB - live telemetry out of the robot.

The event bus (core/events.py) already publishes everything interesting. This
module is where you subscribe to it and forward elsewhere. Three good routes,
roughly in order of effort:

  1. JSONL to disk         - implemented below, works today, zero dependencies
  2. MQTT to a broker      - paho-mqtt, ~20 lines, gives you a live dashboard
  3. WebSocket + web UI    - flask-socketio, lets you watch the camera remotely

Starting with 1 is not a cop-out: having a machine-readable trace of every run
makes your report's evaluation section write itself.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from config import settings
from core.events import Event, bus

log = logging.getLogger(__name__)


class JSONLTelemetry:
    """Subscribes to every event and appends it to logs/telemetry.jsonl."""

    def __init__(self, path: Path = None):
        self.path = path or (settings.LOG_DIR / "telemetry.jsonl")
        self.count = 0

    def attach(self) -> "JSONLTelemetry":
        for event in Event:
            bus.subscribe(event, self._handle)
        log.info("Telemetry -> %s", self.path)
        return self

    def _handle(self, event: Event, **payload):
        self.count += 1
        record = {"ts": time.time(), "event": event.value}
        for k, v in payload.items():
            record[k] = v if isinstance(v, (str, int, float, bool, type(None))) else str(v)
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except OSError:
            pass


# def attach_mqtt(host="localhost"):        # <- your next step
#     import paho.mqtt.client as mqtt
#     client = mqtt.Client(); client.connect(host)
#     for event in Event:
#         bus.subscribe(event, lambda event, **p: client.publish(
#             f"robot/{event.value}", json.dumps(p, default=str)))
