"""
Camera smoke test WITH live mode switching.

    python -m camera.camera_test

Keys:  n = NAVIGATION mode   f = FACE_AUTH mode   i = IDLE   q = quit

Watch the resolution overlay change. This is exactly what happens
automatically when the robot reaches its destination.
"""
import time

import cv2

from core import display

from camera import CameraManager, CameraMode
from config import settings
from core.logging_setup import setup_logging


def main() -> int:
    setup_logging()
    print(f"Platform: {'Raspberry Pi' if settings.IS_PI else 'Laptop'} | "
          f"backend: {settings.CAMERA_BACKEND}")
    for name, spec in settings.CAMERA_MODES.items():
        print(f"  {name:<11} {spec['width']}x{spec['height']} @ {spec['fps']}fps"
              f"  - {spec['description']}")
    print("\nKeys: n/f/i to switch mode, q to quit\n")

    frames, t0 = 0, time.time()
    with CameraManager() as cam:
        while True:
            frame = cam.read()
            if frame is None:
                time.sleep(0.02)
                continue
            frames += 1
            fps = frames / max(time.time() - t0, 1e-6)

            if settings.HEADLESS:
                if frames % 30 == 0:
                    print(f"{cam.mode.value:<11} {frame.shape[1]}x{frame.shape[0]} "
                          f"{fps:.1f} FPS")
                if frames > 200:
                    break
                continue

            cv2.putText(frame, f"{cam.mode.value}  {frame.shape[1]}x{frame.shape[0]}"
                               f"  {fps:5.1f} FPS",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, "n=nav  f=face  i=idle  q=quit",
                        (10, frame.shape[0] - 15), cv2.FONT_HERSHEY_SIMPLEX,
                        0.55, (200, 200, 200), 1)
            display.show("Camera + mode switching", frame)

            k = display.wait_key(1)
            if k == ord("q"):
                break
            if k == ord("n"):
                cam.set_mode(CameraMode.NAVIGATION); frames, t0 = 0, time.time()
            if k == ord("f"):
                cam.set_mode(CameraMode.FACE_AUTH);  frames, t0 = 0, time.time()
            if k == ord("i"):
                cam.set_mode(CameraMode.IDLE);       frames, t0 = 0, time.time()

    display.destroy_all()
    print(f"\n{frames} frames, {cam.switch_count} mode switches.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
