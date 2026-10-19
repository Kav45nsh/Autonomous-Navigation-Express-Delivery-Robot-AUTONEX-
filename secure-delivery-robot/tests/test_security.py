"""
The unlock decision. These are the tests that matter most — everything else
is a robot driving in circles, but this is what opens a box containing
someone else's property.
"""
import time

import pytest

from config import settings
from face_auth.face_authentication import AuthOutcome, FaceAuthenticator, FrameResult
from security.access_controller import AccessController
from security.audit_log import AuditLog
from security.lock_backends.simulated_lock import SimulatedLock
from security.solenoid_lock import SolenoidLock


@pytest.fixture
def controller(tmp_path):
    lock = SolenoidLock(SimulatedLock())
    return AccessController(lock, AuditLog(tmp_path / "audit.jsonl")), lock


# ── lock mechanics ───────────────────────────────────────────
def test_lock_starts_locked():
    assert SolenoidLock(SimulatedLock()).is_unlocked is False


def test_unlock_then_auto_relock():
    lock = SolenoidLock(SimulatedLock())
    assert lock.unlock(duration=0.2) is True
    assert lock.is_unlocked is True
    assert lock.wait_until_locked(2.0) is True      # relocked on its own


def test_double_unlock_is_rejected():
    lock = SolenoidLock(SimulatedLock())
    lock.unlock(duration=0.5)
    assert lock.unlock(duration=0.5) is False
    lock.lock()


def test_unlock_duration_capped_by_coil_limit():
    lock = SolenoidLock(SimulatedLock())
    lock.unlock(duration=9999)
    assert lock.is_unlocked
    lock.lock()      # capped at MAX_CONTINUOUS_ENERGISE_S, never held forever


def test_cleanup_is_fail_secure():
    device = SimulatedLock()
    with SolenoidLock(device) as lock:
        lock.unlock(duration=30)
        assert lock.is_unlocked
    assert device.is_unlocked is False      # exiting the block locks it


# ── access policy ────────────────────────────────────────────
def test_authorised_outcome_unlocks(controller):
    ctrl, lock = controller
    d = ctrl.handle(AuthOutcome(True, "Priya", 0.72, "authorised"))
    assert d.granted and d.unlocked and lock.is_unlocked
    lock.lock()


def test_unauthorised_outcome_keeps_lock_shut(controller):
    ctrl, lock = controller
    d = ctrl.handle(AuthOutcome(False, None, 0.31, "below threshold"))
    assert d.granted is False and lock.is_unlocked is False


def test_controller_rechecks_threshold_itself(controller):
    """Defence in depth: even a mislabelled 'authorised' outcome is caught."""
    ctrl, lock = controller
    d = ctrl.handle(AuthOutcome(True, "Impostor", 0.20, "authorised"))
    assert d.granted is False
    assert lock.is_unlocked is False


def test_every_decision_is_audited(controller, tmp_path):
    ctrl, lock = controller
    ctrl.handle(AuthOutcome(True, "Priya", 0.80, "authorised"))
    ctrl.handle(AuthOutcome(False, None, 0.10, "no match"))
    lock.lock()
    entries = ctrl.audit.read_all()
    assert [e["event"] for e in entries] == ["DELIVERY_GRANTED", "DELIVERY_DENIED"]
    assert entries[0]["recipient"] == "Priya"
    assert "threshold" in entries[0]


# ── the streak requirement ───────────────────────────────────
def _auth_with_stub():
    from face_auth.face_database import FaceDatabase
    import numpy as np
    db = FaceDatabase(people={"Priya": [np.zeros(128)]})
    a = FaceAuthenticator.__new__(FaceAuthenticator)
    a.db, a.encoder = db, None
    a._streak_name, a._streak, a._frames = None, 0, 0
    a.attempts, a._locked_until = 0, 0.0
    return a


def test_single_good_frame_does_not_unlock():
    a = _auth_with_stub()
    good = FrameResult("Priya", 0.75, 0.30, True, 1, (0, 1, 1, 0), "candidate")
    assert a.update_streak(good) is None          # one frame is not enough


def test_streak_of_required_length_confirms():
    a = _auth_with_stub()
    good = FrameResult("Priya", 0.75, 0.30, True, 1, (0, 1, 1, 0), "candidate")
    result = None
    for _ in range(settings.AUTH_REQUIRED_STREAK):
        result = a.update_streak(good)
    assert result == "Priya"


def test_interruption_resets_the_streak():
    a = _auth_with_stub()
    good = FrameResult("Priya", 0.75, 0.30, True, 1, (0, 1, 1, 0), "candidate")
    bad = FrameResult(None, 0.20, 0.0, False, 0, None, "no face")
    a.update_streak(good); a.update_streak(good)
    a.update_streak(bad)                          # someone stepped away
    assert a.streak_progress[0] == 0


def test_switching_identity_restarts_streak():
    a = _auth_with_stub()
    p = FrameResult("Priya", 0.75, 0.30, True, 1, (0, 1, 1, 0), "candidate")
    r = FrameResult("Rahul", 0.71, 0.25, True, 1, (0, 1, 1, 0), "candidate")
    a.update_streak(p); a.update_streak(p)
    a.update_streak(r)
    assert a.streak_progress[0] == 1              # counts for Rahul, not Priya


def test_frame_below_threshold_is_never_a_candidate():
    low = FrameResult(None, 0.49, 0.30, False, 1, None, "below threshold")
    assert low.is_candidate is False
