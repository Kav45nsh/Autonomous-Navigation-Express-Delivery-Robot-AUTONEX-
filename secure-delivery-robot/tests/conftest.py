"""Shared fixtures. All tests run with zero hardware."""
import numpy as np
import pytest

from qr_navigation.qr_detector import QRDetection


@pytest.fixture
def make_detection():
    def _make(data="WP-DEST-01", cx=320, area=30000):
        pts = np.array([[cx - 60, 100], [cx + 60, 100],
                        [cx + 60, 220], [cx - 60, 220]], dtype=np.float32)
        return QRDetection(data=data, points=pts, center=(cx, 160), area=area)
    return _make


@pytest.fixture
def fake_camera():
    """A CameraSource that records configure() calls - proves mode switching."""
    from core.interfaces import CameraSource

    class FakeCamera(CameraSource):
        def __init__(self):
            self.configs = []
            self.opened = False
            self.frames_read = 0

        def open(self):
            self.opened = True

        def configure(self, width, height, fps):
            self.configs.append((width, height, fps))

        def read(self):
            self.frames_read += 1
            return np.zeros((48, 64, 3), dtype=np.uint8)

        def close(self):
            self.opened = False

    return FakeCamera()
