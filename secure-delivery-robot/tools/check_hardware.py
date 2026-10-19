"""
Pre-flight diagnostics. Run this FIRST on the Pi, before main.py.

    python tools/check_hardware.py

Checks each subsystem independently and tells you exactly what is missing.
Far faster than decoding an ImportError traceback at 2am.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings

OK, BAD, WARN = "  [ OK ]", "  [FAIL]", "  [WARN]"


def check(label, fn):
    try:
        detail = fn()
        print(f"{OK} {label}" + (f" - {detail}" if detail else ""))
        return True
    except Exception as e:
        print(f"{BAD} {label} - {type(e).__name__}: {e}")
        return False


def main():
    print("=" * 60)
    print("  HARDWARE PRE-FLIGHT")
    print("=" * 60)
    print(f"  platform detected : {settings.detect_platform()}")
    print(f"  camera / motors   : {settings.CAMERA_BACKEND} / {settings.MOTOR_BACKEND}")
    print(f"  lock / range      : {settings.LOCK_BACKEND} / {settings.RANGE_BACKEND}")
    print(f"  face engine       : {settings.FACE_BACKEND}")
    print("-" * 60)

    results = []

    results.append(check("OpenCV", lambda: __import__("cv2").__version__))
    results.append(check("NumPy", lambda: __import__("numpy").__version__))

    def _camera():
        from camera import CameraManager, CameraMode
        cam = CameraManager().open()
        f = cam.read()
        if f is None:
            raise RuntimeError("opened but returned no frame")
        shape = f"{f.shape[1]}x{f.shape[0]}"
        cam.set_mode(CameraMode.FACE_AUTH)
        f2 = cam.read()
        cam.close()
        return f"{shape} -> {f2.shape[1]}x{f2.shape[0]} on mode switch"
    results.append(check("Camera + mode switching", _camera))

    def _face():
        from face_auth.face_encoder import FaceEncoder
        return f"{FaceEncoder().backend} backend ready"
    results.append(check("Face engine", _face))

    def _db():
        from face_auth.face_database import FaceDatabase
        db = FaceDatabase.load()
        if db.is_empty:
            raise RuntimeError("nobody enrolled - run face_registration")
        return db.summary()
    results.append(check("Enrolled recipients", _db))

    def _motors():
        from navigation.movement_controller import build_motors
        m = build_motors()
        m.set_speeds(0, 0)
        m.cleanup()
        return type(m).__name__
    results.append(check("Motors", _motors))

    def _lock():
        from security.solenoid_lock import build_lock_device
        d = build_lock_device()
        if d.is_unlocked:
            raise RuntimeError("lock did NOT start in the locked state")
        d.cleanup()
        return f"{type(d).__name__}, starts locked"
    results.append(check("Solenoid lock", _lock))

    def _range():
        from obstacle.obstacle_detector import build_range_sensor
        s = build_range_sensor()
        cm = s.read_cm()
        s.cleanup()
        return f"{cm:.0f} cm" if cm else "no reading"
    results.append(check("Range sensor", _range))

    def _voice():
        from voice.voice import VoiceAnnouncer
        v = VoiceAnnouncer(settings.VOICE_BACKEND)
        v.start()
        v.stop()
        return v.backend
    results.append(check("Voice", _voice))

    if settings.ESP32_ENABLED:
        def _esp():
            from communication.esp32_serial import ESP32Serial
            e = ESP32Serial()
            e.connect()
            e.close()
            return settings.ESP32_PORT
        results.append(check("ESP32 link", _esp))

    print("-" * 60)
    passed = sum(results)
    print(f"  {passed}/{len(results)} subsystems OK")
    print("=" * 60)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
