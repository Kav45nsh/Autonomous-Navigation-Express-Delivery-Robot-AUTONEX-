"""
Safe wrappers around cv2 GUI calls.

A headless OpenCV build (which is what you get on a Pi with
opencv-python-headless, and what any Pi without a desktop session needs)
raises on imshow/destroyAllWindows rather than no-opping. Crashing during
SHUTDOWN is the worst possible time, because it skips the code that relocks
the compartment. These wrappers make GUI calls always safe to make.
"""
import logging

import cv2

from config import settings

log = logging.getLogger(__name__)
_WARNED = False


def gui_available() -> bool:
    return not settings.HEADLESS


def show(window: str, frame) -> None:
    global _WARNED
    if settings.HEADLESS or frame is None:
        return
    try:
        cv2.imshow(window, frame)
    except cv2.error:
        if not _WARNED:
            log.warning("OpenCV has no GUI support - forcing HEADLESS mode")
            _WARNED = True
        settings.HEADLESS = True


def wait_key(delay: int = 1) -> int:
    if settings.HEADLESS:
        return -1
    try:
        return cv2.waitKey(delay) & 0xFF
    except cv2.error:
        settings.HEADLESS = True
        return -1


def destroy_all() -> None:
    """Never raises. Safe to call in a finally block."""
    try:
        cv2.destroyAllWindows()
    except Exception:
        pass
