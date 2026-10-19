"""
Tiny synchronous event bus.

Why it exists: it is the seam for future scope. A web dashboard, an MQTT
bridge, a Telegram notifier or a CSV recorder can subscribe to robot events
without a single line changing inside navigation or security.

    from core.events import bus, Event
    bus.subscribe(Event.UNLOCKED, lambda **kw: print(kw))
    bus.emit(Event.UNLOCKED, recipient="Priya", confidence=0.71)
"""
from __future__ import annotations

import logging
from collections import defaultdict
from enum import Enum
from typing import Callable, DefaultDict, List

log = logging.getLogger(__name__)


class Event(str, Enum):
    STARTED = "started"
    MODE_CHANGED = "camera_mode_changed"
    MARKER_SEEN = "marker_seen"
    COMMAND_EXECUTED = "command_executed"
    OBSTACLE_DETECTED = "obstacle_detected"
    OBSTACLE_CLEARED = "obstacle_cleared"
    ARRIVED = "arrived"
    AUTH_STARTED = "auth_started"
    AUTH_FRAME = "auth_frame"
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILED = "auth_failed"
    UNLOCKED = "unlocked"
    RELOCKED = "relocked"
    DELIVERED = "delivered"
    ERROR = "error"
    SHUTDOWN = "shutdown"


class EventBus:
    def __init__(self):
        self._subs: DefaultDict[Event, List[Callable]] = defaultdict(list)

    def subscribe(self, event: Event, handler: Callable) -> None:
        self._subs[event].append(handler)

    def emit(self, event: Event, **payload) -> None:
        for handler in self._subs.get(event, ()):
            try:
                handler(event=event, **payload)
            except Exception:
                log.exception("Event handler failed for %s", event)


bus = EventBus()
