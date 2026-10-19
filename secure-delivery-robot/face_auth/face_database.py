"""
Enrolled recipients.

Replaces a single authorized_face.jpg. One photo gives you one lighting
condition, one angle, one expression — and a system that fails the moment the
recipient stands somewhere slightly different. Multiple samples per person is
the single cheapest accuracy improvement available to you.

Photos land in data/faces/known/<Name>/, encodings cache to a pickle.
Both are gitignored: biometric data must never enter version control.
"""
from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np

from config import settings

log = logging.getLogger(__name__)


@dataclass
class FaceDatabase:
    backend: str = field(default_factory=lambda: settings.FACE_BACKEND)
    people: Dict[str, List[np.ndarray]] = field(default_factory=dict)

    # ───────────────────────────────────── persistence
    @classmethod
    def load(cls) -> "FaceDatabase":
        path = settings.ENCODINGS_FILE
        if not path.exists():
            log.info("No encodings yet at %s", path)
            return cls()
        with open(path, "rb") as f:
            raw = pickle.load(f)
        db = cls(backend=raw.get("backend", settings.FACE_BACKEND),
                 people=raw.get("people", {}))
        if db.backend != settings.FACE_BACKEND:
            log.warning("Encodings built with %r but FACE_BACKEND is %r. "
                        "Re-enroll everyone.", db.backend, settings.FACE_BACKEND)
        log.info("Loaded %d people / %d samples", len(db.people), db.sample_count)
        return db

    def save(self) -> None:
        with open(settings.ENCODINGS_FILE, "wb") as f:
            pickle.dump({"backend": self.backend, "people": self.people}, f)
        log.info("Saved %d people to %s", len(self.people), settings.ENCODINGS_FILE)

    # ───────────────────────────────────── data
    @property
    def sample_count(self) -> int:
        return sum(len(v) for v in self.people.values())

    @property
    def is_empty(self) -> bool:
        return not self.people

    def add(self, name: str, encoding: np.ndarray) -> None:
        self.people.setdefault(name, []).append(encoding)

    def remove(self, name: str) -> bool:
        return self.people.pop(name, None) is not None

    def flat(self) -> Tuple[List[np.ndarray], List[str]]:
        encs, names = [], []
        for name, samples in self.people.items():
            encs.extend(samples)
            names.extend([name] * len(samples))
        return encs, names

    def summary(self) -> str:
        if self.is_empty:
            return "(nobody enrolled)"
        return ", ".join(f"{n} x{len(v)}" for n, v in self.people.items())
