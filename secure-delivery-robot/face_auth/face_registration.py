"""
Enroll authorised recipients.

    python -m face_auth.face_registration --name "Priya Sharma" --samples 6
    python -m face_auth.face_registration --list
    python -m face_auth.face_registration --delete "Priya Sharma"
    python -m face_auth.face_registration --name "X" --from-folder path/to/pics

SPACE captures, q finishes. Vary angle, distance and lighting between shots —
that matters far more than the number of samples. Six varied beats twenty
identical.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import cv2

from core import display

from config import settings
from core.logging_setup import setup_logging
from face_auth.face_database import FaceDatabase
from face_auth.face_encoder import FaceEncoder

log = logging.getLogger(__name__)


def from_camera(name: str, target: int) -> int:
    from camera import CameraManager, CameraMode

    encoder, db = FaceEncoder(), FaceDatabase.load()
    photo_dir = settings.FACES_DIR / name.replace(" ", "_")
    photo_dir.mkdir(parents=True, exist_ok=True)
    captured = 0

    print(f"Enrolling '{name}'. SPACE = capture, q = done.")
    with CameraManager() as cam:
        cam.set_mode(CameraMode.FACE_AUTH)   # enroll at the SAME resolution
        while captured < target:             # we will authenticate at
            frame = cam.read()
            if frame is None:
                continue
            encs, boxes = encoder.encode(frame)
            for (t, r, b, l) in boxes:
                cv2.rectangle(frame, (l, t), (r, b), (0, 255, 0), 2)

            msg = f"{name}  {captured}/{target}"
            if not encs:
                msg += "  - no face"
            elif len(encs) > 1:
                msg += "  - MULTIPLE faces, one person only"
            cv2.putText(frame, msg, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (0, 255, 255), 2)
            cv2.putText(frame, "vary your angle and distance between shots",
                        (10, frame.shape[0] - 15), cv2.FONT_HERSHEY_SIMPLEX,
                        0.55, (200, 200, 200), 1)
            display.show("Register - SPACE to capture, q to quit", frame)

            k = display.wait_key(1)
            if k == ord("q"):
                break
            if k == ord(" ") and len(encs) == 1:
                db.add(name, encs[0])
                cv2.imwrite(str(photo_dir / f"{captured:02d}.jpg"), frame)
                captured += 1
                print(f"  {captured}/{target}")

    display.destroy_all()
    if captured:
        db.save()
        print(f"Enrolled '{name}' with {captured} samples. DB: {db.summary()}")
    else:
        print("Nothing captured.")
    return 0


def from_folder(name: str, folder: str) -> int:
    encoder, db = FaceEncoder(), FaceDatabase.load()
    added = 0
    for p in sorted(Path(folder).glob("*")):
        if p.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue
        img = cv2.imread(str(p))
        encs, _ = encoder.encode(img)
        if len(encs) == 1:
            db.add(name, encs[0])
            added += 1
            print(f"  + {p.name}")
        else:
            print(f"  - {p.name} ({len(encs)} faces, need exactly 1)")
    if added:
        db.save()
    print(f"Added {added} samples for '{name}'.")
    return 0


def main() -> int:
    setup_logging()
    p = argparse.ArgumentParser(description="Register an authorised recipient")
    p.add_argument("--name")
    p.add_argument("--samples", type=int, default=6)
    p.add_argument("--from-folder", help="Enroll from existing photos instead")
    p.add_argument("--list", action="store_true")
    p.add_argument("--delete", metavar="NAME")
    a = p.parse_args()

    if a.list:
        db = FaceDatabase.load()
        print(f"Backend: {db.backend}\n{db.summary()}")
        return 0
    if a.delete:
        db = FaceDatabase.load()
        print("deleted" if db.remove(a.delete) else "not found")
        db.save()
        return 0
    if not a.name:
        p.error("--name is required")
    if a.from_folder:
        return from_folder(a.name, a.from_folder)
    return from_camera(a.name, a.samples)


if __name__ == "__main__":
    raise SystemExit(main())
