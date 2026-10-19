"""
Marker confirmation / locking behaviour. Covers spec test cases 2-8.

These tests monkeypatch the timing settings down to a few milliseconds so
the suite stays fast - the LOGIC under test (stable frames -> confirmation
timer -> lock -> reset) is identical to the 3-frame / 5-second production
values, just compressed in time.
"""
import time

import pytest

from config import settings
from qr_navigation.marker_handler import MarkerHandler


@pytest.fixture(autouse=True)
def fast_timings(monkeypatch):
    monkeypatch.setattr(settings, "QR_STABLE_FRAMES", 3)
    monkeypatch.setattr(settings, "QR_CONFIRMATION_TIME", 0.15)
    monkeypatch.setattr(settings, "QR_LOST_FRAMES", 2)


def _confirm(handler: MarkerHandler, marker: str) -> None:
    """Drive the handler until `marker` is confirmed (case 4)."""
    for _ in range(settings.QR_STABLE_FRAMES):
        handler.update(marker)
    time.sleep(settings.QR_CONFIRMATION_TIME + 0.02)
    status = handler.update(marker)
    assert status.just_confirmed == marker


# case 2: detected once -> no immediate command
def test_single_detection_is_not_enough():
    h = MarkerHandler()
    status = h.update("MARKER 2")
    assert status.just_confirmed is None


# case 3: stable detection starts the confirmation timer
def test_stable_frames_start_confirmation():
    h = MarkerHandler()
    for _ in range(settings.QR_STABLE_FRAMES):
        status = h.update("MARKER 2")
    assert status.confirming is True
    assert status.just_confirmed is None


# case 4: remains visible for the full confirmation time -> accepted
def test_confirmation_time_elapsed_accepts_command():
    h = MarkerHandler()
    _confirm(h, "MARKER 2")


# case 5: remains visible -> command is NOT accepted again
def test_locked_marker_does_not_refire_while_visible():
    h = MarkerHandler()
    _confirm(h, "MARKER 2")
    for _ in range(5):
        status = h.update("MARKER 2")
        assert status.just_confirmed is None
        assert status.locked is True


# case 6 + 7: disappears -> resets -> can be accepted again later
def test_marker_can_be_reaccepted_after_disappearing():
    h = MarkerHandler()
    _confirm(h, "MARKER 2")

    for _ in range(settings.QR_LOST_FRAMES):
        h.update(None)

    # fully reset now
    _confirm(h, "MARKER 2")


# case 8: a different marker gets its own, independent confirmation
def test_different_marker_confirms_independently():
    h = MarkerHandler()
    _confirm(h, "MARKER 2")
    _confirm(h, "MARKER 4")


def test_confirmation_resets_if_marker_disappears_mid_timer():
    h = MarkerHandler()
    for _ in range(settings.QR_STABLE_FRAMES):
        h.update("MARKER 3")
    # gone before the timer completes
    for _ in range(settings.QR_LOST_FRAMES):
        h.update(None)
    status = h.update("MARKER 3")
    assert status.stable_frames == 1
    assert status.just_confirmed is None
