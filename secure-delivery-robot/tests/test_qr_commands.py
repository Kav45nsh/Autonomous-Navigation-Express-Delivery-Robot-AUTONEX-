"""QR payload -> command mapping. Covers test cases 1 and 13-16 from the spec
(unrecognised QR ignored; before-START gating is exercised at the Navigator
level in test_navigation.py, since QRCommandHandler itself has no concept of
"started")."""
from qr_navigation.qr_commands import QRCommandHandler


def test_known_markers_map_correctly():
    h = QRCommandHandler()
    assert h.parse("MARKER 1") == "START"
    assert h.parse("MARKER 2") == "STRAIGHT"
    assert h.parse("MARKER 3") == "RIGHT"
    assert h.parse("MARKER 4") == "LEFT"
    assert h.parse("MARKER 5") == "DESTINATION"
    assert h.parse("STOP") == "STOP"


def test_case_and_whitespace_insensitive():
    h = QRCommandHandler()
    assert h.parse("  marker 2  ") == "STRAIGHT"
    assert h.parse("stop") == "STOP"


def test_unknown_qr_is_ignored():
    h = QRCommandHandler()
    assert h.parse("NONSENSE") is None
    assert h.parse("") is None
    assert h.parse(None) is None


def test_stop_and_destination_are_different_commands():
    h = QRCommandHandler()
    assert h.parse("STOP") != h.parse("MARKER 5")
