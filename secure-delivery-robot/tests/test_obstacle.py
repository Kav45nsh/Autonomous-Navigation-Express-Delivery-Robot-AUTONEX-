"""
Obstacle avoidance: the "think about it" clearance decision and the
temporary-deviation-then-return behaviour. Covers spec test cases 17-25.
"""
import pytest

from config import settings
from navigation.movement_controller import MovementController
from navigation.motors.simulated import SimulatedMotors
from obstacle.obstacle_avoidance import AvoidancePhase, ObstacleAvoidance
from obstacle.obstacle_detector import ObstacleDetector
from obstacle.sensors.simulated_range import SimulatedRangeSensor


@pytest.fixture(autouse=True)
def fast_timings(monkeypatch):
    monkeypatch.setattr(settings, "AVOIDANCE_TURN_DURATION", 0)
    monkeypatch.setattr(settings, "AVOIDANCE_FORWARD_DURATION", 0)
    monkeypatch.setattr(settings, "OBSTACLE_RECHECK_INTERVAL", 0)


@pytest.fixture
def rig():
    front, left, right = (SimulatedRangeSensor(), SimulatedRangeSensor(),
                          SimulatedRangeSensor())
    detector = ObstacleDetector(front, left, right)
    avoidance = ObstacleAvoidance(detector)
    movement = MovementController(SimulatedMotors())
    return avoidance, movement, front, left, right


REQUIRED_SIDE = settings.ROBOT_WIDTH_CM + settings.SIDE_SAFETY_MARGIN_CM


# case 17: no obstacle -> stays clear
def test_no_obstacle_stays_clear(rig):
    avoidance, movement, front, left, right = rig
    front.force(200.0); left.force(200.0); right.force(200.0)
    assert avoidance.update(movement) is AvoidancePhase.CLEAR


# case 18: front obstacle -> robot stops
def test_front_obstacle_stops_robot(rig):
    avoidance, movement, front, left, right = rig
    movement.move_forward()
    front.force(settings.FRONT_SAFE_DISTANCE_CM - 5)
    left.force(200.0); right.force(200.0)
    avoidance.update(movement)
    assert movement.is_stopped is True


def _drive_to_checking(avoidance, movement):
    avoidance.update(movement)   # CLEAR -> OBSTACLE_DETECTED
    avoidance.update(movement)   # OBSTACLE_DETECTED -> OBSTACLE_CHECKING
    return avoidance.update(movement)   # OBSTACLE_CHECKING -> a decision


# case 19: front blocked, left clear, right blocked -> choose left
def test_chooses_left_when_only_left_is_clear(rig):
    avoidance, movement, front, left, right = rig
    front.force(10.0)
    left.force(REQUIRED_SIDE + 20)
    right.force(REQUIRED_SIDE - 20)
    phase = _drive_to_checking(avoidance, movement)
    assert phase is AvoidancePhase.AVOIDING_LEFT
    assert avoidance.chosen_side == "LEFT"


# case 20: front blocked, right clear, left blocked -> choose right
def test_chooses_right_when_only_right_is_clear(rig):
    avoidance, movement, front, left, right = rig
    front.force(10.0)
    left.force(REQUIRED_SIDE - 20)
    right.force(REQUIRED_SIDE + 20)
    phase = _drive_to_checking(avoidance, movement)
    assert phase is AvoidancePhase.AVOIDING_RIGHT
    assert avoidance.chosen_side == "RIGHT"


# case 21: both sides blocked -> remain stopped, keep re-checking
def test_both_sides_blocked_remains_stopped(rig):
    avoidance, movement, front, left, right = rig
    front.force(10.0)
    left.force(REQUIRED_SIDE - 20)
    right.force(REQUIRED_SIDE - 20)
    phase = _drive_to_checking(avoidance, movement)
    assert phase is AvoidancePhase.OBSTACLE_STOP
    assert movement.is_stopped is True

    # still blocked next tick -> stays stopped, does not give up
    front.force(10.0); left.force(REQUIRED_SIDE - 20); right.force(REQUIRED_SIDE - 20)
    assert avoidance.update(movement) is AvoidancePhase.OBSTACLE_STOP


# case 22: obstacle clears before a side is committed to -> resume
def test_obstacle_clearing_resumes_immediately(rig):
    avoidance, movement, front, left, right = rig
    front.force(10.0); left.force(0.0); right.force(0.0)
    avoidance.update(movement)                     # OBSTACLE_DETECTED
    front.force(200.0)                             # obstacle walked away
    phase = avoidance.update(movement)
    assert phase is AvoidancePhase.CLEAR


# case 23/24: original command STRAIGHT must survive an avoidance cycle
def test_avoidance_never_touches_desired_command(rig):
    from navigation.navigation import Navigator

    avoidance, movement, front, left, right = rig
    navigator = Navigator(movement)
    navigator.desired_command = "STRAIGHT"
    navigator.started = True

    front.force(10.0)
    left.force(REQUIRED_SIDE + 20)
    right.force(REQUIRED_SIDE - 20)

    for _ in range(2):
        avoidance.update(movement)
    phase = avoidance.update(movement)              # -> AVOIDING_LEFT
    assert phase is AvoidancePhase.AVOIDING_LEFT
    assert navigator.desired_command == "STRAIGHT"      # untouched

    phase = avoidance.update(movement)              # -> RETURNING_TO_PATH
    assert navigator.desired_command == "STRAIGHT"

    front.force(200.0); left.force(200.0); right.force(200.0)
    phase = avoidance.update(movement)              # -> CLEAR
    assert phase is AvoidancePhase.CLEAR
    assert navigator.desired_command == "STRAIGHT"
    navigator.resume_after_avoidance()
    assert movement.is_stopped is False             # moving straight again


# case 25: safety overrides forward movement even mid-STRAIGHT
def test_front_obstacle_overrides_forward_motion(rig):
    avoidance, movement, front, left, right = rig
    movement.move_forward()
    assert movement.is_stopped is False
    front.force(5.0); left.force(200.0); right.force(200.0)
    avoidance.update(movement)
    assert movement.is_stopped is True
