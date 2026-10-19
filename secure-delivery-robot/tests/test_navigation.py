"""
Navigator behaviour: START gating, discrete turns, STOP vs DESTINATION.
Covers spec test cases 9-16 and 26/27/31 at the unit level (26-31's actual
face-authentication hand-off is exercised in test_destination_auth.py).
"""
import pytest

from config import settings
from navigation.movement_controller import MovementController
from navigation.motors.simulated import SimulatedMotors
from navigation.navigation import Navigator
from navigation.robot_state import RobotState


@pytest.fixture(autouse=True)
def fast_confirmation(monkeypatch):
    # Confirm on the very first frame so tests don't need to sleep.
    monkeypatch.setattr(settings, "QR_STABLE_FRAMES", 1)
    monkeypatch.setattr(settings, "QR_CONFIRMATION_TIME", 0)
    monkeypatch.setattr(settings, "QR_LOST_FRAMES", 1)
    monkeypatch.setattr(settings, "TURN_DURATION", 0)          # instant in tests
    monkeypatch.setattr(settings, "AVOIDANCE_TURN_DURATION", 0)


@pytest.fixture
def nav():
    motors = SimulatedMotors()
    return Navigator(MovementController(motors)), motors


def _confirm(nav, marker):
    # First sighting always just starts tracking; the second sighting is
    # "stable" (QR_STABLE_FRAMES=1) and, with QR_CONFIRMATION_TIME=0,
    # confirms immediately.
    nav.step(marker)
    nav.step(marker)
    nav.step(None)            # marker "disappears" so it can be seen again later


# ── case 13-16: nothing before MARKER 1 ─────────────────────────
@pytest.mark.parametrize("marker", ["MARKER 2", "MARKER 3", "MARKER 4", "MARKER 5"])
def test_markers_ignored_before_start(nav, marker):
    navigator, motors = nav
    _confirm(navigator, marker)
    assert navigator.started is False
    assert (motors.left, motors.right) == (0.0, 0.0)
    assert navigator.fsm.state is RobotState.WAITING_FOR_START


def test_marker1_starts_the_robot(nav):
    navigator, motors = nav
    _confirm(navigator, "MARKER 1")
    assert navigator.started is True
    assert navigator.desired_command == "STRAIGHT"
    assert motors.left == motors.right > 0
    assert navigator.fsm.state is RobotState.MOVING_FORWARD


# ── case 9/10: exactly one turn, then back to straight ──────────
def test_marker3_performs_one_right_turn_then_straight(nav):
    navigator, motors = nav
    _confirm(navigator, "MARKER 1")
    _confirm(navigator, "MARKER 3")
    assert navigator.desired_command == "STRAIGHT"
    assert navigator.fsm.state is RobotState.MOVING_FORWARD
    # moving forward again afterwards, not still spinning
    assert motors.left == motors.right > 0


def test_marker4_performs_one_left_turn_then_straight(nav):
    navigator, motors = nav
    _confirm(navigator, "MARKER 1")
    _confirm(navigator, "MARKER 4")
    assert navigator.desired_command == "STRAIGHT"
    assert navigator.fsm.state is RobotState.MOVING_FORWARD


def test_repeated_straight_markers_are_all_handled(nav):
    navigator, _ = nav
    _confirm(navigator, "MARKER 1")
    for _ in range(3):
        _confirm(navigator, "MARKER 2")
    assert navigator.desired_command == "STRAIGHT"
    assert navigator.fsm.state is RobotState.MOVING_FORWARD


# ── case 11/26/27: destination stops the robot and ends QR nav ──
def test_marker5_stops_robot_and_flags_destination(nav):
    navigator, motors = nav
    _confirm(navigator, "MARKER 1")
    _confirm(navigator, "MARKER 5")
    assert navigator.destination_reached is True
    assert navigator.desired_command is None
    assert (motors.left, motors.right) == (0.0, 0.0)
    assert navigator.fsm.state is RobotState.DESTINATION


# ── case 12/31: STOP halts but is NOT destination ────────────────
def test_stop_marker_halts_without_destination(nav):
    navigator, motors = nav
    _confirm(navigator, "MARKER 1")
    _confirm(navigator, "STOP")
    assert navigator.stopped_by_qr is True
    assert navigator.destination_reached is False
    assert (motors.left, motors.right) == (0.0, 0.0)
    assert navigator.fsm.state is RobotState.STOPPED_BY_QR


# ── case 26/27/28: destination truly stops QR navigation ────────
def test_qr_navigation_ignores_further_markers_after_destination(nav):
    navigator, motors = nav
    _confirm(navigator, "MARKER 1")
    _confirm(navigator, "MARKER 5")
    assert navigator.fsm.state is RobotState.DESTINATION

    before = (motors.left, motors.right)
    _confirm(navigator, "MARKER 2")   # main.py would have stopped calling
    navigator.step("MARKER 3")        # step() here too, but even if called...
    assert (motors.left, motors.right) == before   # ...nothing moves again


def test_unknown_qr_does_nothing(nav):
    navigator, motors = nav
    _confirm(navigator, "MARKER 1")
    before = (motors.left, motors.right)
    _confirm(navigator, "GARBAGE")
    assert (motors.left, motors.right) == before
    assert navigator.fsm.state is RobotState.MOVING_FORWARD
