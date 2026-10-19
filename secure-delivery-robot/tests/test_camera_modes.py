"""The camera mode switch - the feature the whole mission depends on."""
import pytest

from camera.camera_manager import CameraManager, CameraMode
from config import settings


def test_opens_in_navigation_mode(fake_camera):
    cam = CameraManager(fake_camera).open()
    assert cam.mode is CameraMode.NAVIGATION
    assert fake_camera.configs[-1] == (640, 480, 30)


def test_switch_to_face_auth_raises_resolution(fake_camera, monkeypatch):
    monkeypatch.setattr(settings, "MODE_SWITCH_SETTLE_SECONDS", 0.0)
    cam = CameraManager(fake_camera).open()
    nav_res = cam.resolution
    assert cam.set_mode(CameraMode.FACE_AUTH) is True
    assert cam.mode is CameraMode.FACE_AUTH
    assert cam.resolution == (1280, 720)
    assert cam.resolution[0] > nav_res[0]      # more pixels on the face
    assert fake_camera.configs[-1] == (1280, 720, 15)


def test_switch_is_idempotent(fake_camera, monkeypatch):
    monkeypatch.setattr(settings, "MODE_SWITCH_SETTLE_SECONDS", 0.0)
    cam = CameraManager(fake_camera).open()
    assert cam.set_mode(CameraMode.FACE_AUTH) is True
    assert cam.set_mode(CameraMode.FACE_AUTH) is False   # no second reconfigure
    n = len(fake_camera.configs)
    cam.face_auth_mode()
    assert len(fake_camera.configs) == n


def test_settling_drains_stale_frames(fake_camera, monkeypatch):
    monkeypatch.setattr(settings, "MODE_SWITCH_SETTLE_SECONDS", 0.05)
    cam = CameraManager(fake_camera).open()
    before = fake_camera.frames_read
    cam.set_mode(CameraMode.FACE_AUTH)
    assert fake_camera.frames_read > before    # bad frames thrown away


def test_can_switch_back_to_navigation(fake_camera, monkeypatch):
    monkeypatch.setattr(settings, "MODE_SWITCH_SETTLE_SECONDS", 0.0)
    cam = CameraManager(fake_camera).open()
    cam.face_auth_mode()
    cam.navigation_mode()
    assert cam.mode is CameraMode.NAVIGATION
    assert cam.switch_count == 3
