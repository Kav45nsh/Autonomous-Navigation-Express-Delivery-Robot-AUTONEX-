"""
Line protocol for the Pi <-> ESP32 link.

Deliberately human-readable ASCII: you can open a serial monitor and see
exactly what is being exchanged, which saves hours when the link misbehaves.

    CMD:MOVE:0.55,0.55\n        Pi  -> ESP32
    EVT:RANGE:42.5\n            ESP32 -> Pi
    ACK:MOVE\n                  ESP32 -> Pi

A checksum field is included and validated. Long motor runs inject electrical
noise into serial lines, and a corrupted speed command is worth catching.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


def checksum(payload: str) -> int:
    """XOR of all bytes - cheap and adequate for this link."""
    c = 0
    for ch in payload.encode("utf-8"):
        c ^= ch
    return c


@dataclass
class Message:
    kind: str                  # CMD | EVT | ACK | ERR
    name: str
    args: List[str]

    def encode(self) -> str:
        body = f"{self.kind}:{self.name}"
        if self.args:
            body += ":" + ",".join(str(a) for a in self.args)
        return f"{body}*{checksum(body):02X}"

    @classmethod
    def decode(cls, line: str) -> Optional["Message"]:
        line = line.strip()
        if not line:
            return None
        if "*" in line:
            body, _, got = line.rpartition("*")
            try:
                if int(got, 16) != checksum(body):
                    return None        # corrupted
            except ValueError:
                return None
        else:
            body = line
        parts = body.split(":")
        if len(parts) < 2:
            return None
        kind, name = parts[0], parts[1]
        args = parts[2].split(",") if len(parts) > 2 and parts[2] else []
        return cls(kind, name, args)


# Convenience constructors
def move(left: float, right: float) -> Message:
    return Message("CMD", "MOVE", [f"{left:.2f}", f"{right:.2f}"])


def unlock(seconds: float) -> Message:
    return Message("CMD", "UNLOCK", [f"{seconds:.1f}"])


def stop() -> Message:
    return Message("CMD", "STOP", [])


def ping() -> Message:
    return Message("CMD", "PING", [])
