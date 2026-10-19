# Setup

## Laptop (development)

```bash
git clone <your-repo> && cd secure-delivery-robot
python -m venv venv
source venv/bin/activate         # Windows: venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env             # optional
```

**VS Code**: Ctrl+Shift+P → *Python: Select Interpreter* → pick `./venv`.
Install the **Python** and **Pylance** extensions. `.vscode/launch.json` has
nine numbered run configs; press F5 and pick one.

Verify in order — do not skip ahead:

```bash
python tools/check_hardware.py
python -m camera.camera_test                  # press n / f / i
python tools/generate_qr.py
python -m qr_navigation.qr_detector
python -m face_auth.face_registration --name "Your Name" --samples 6
python -m face_auth.face_authentication
python -m navigation.navigation
python main.py --simulate
pytest -q
```

---

## Raspberry Pi 4 (deployment)

### 1. System packages (apt, not pip)

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y python3-pip python3-venv python3-dev \
  python3-picamera2 python3-gpiozero python3-lgpio \
  libzbar0 espeak espeak-ng \
  cmake build-essential libopenblas-dev liblapack-dev \
  libatlas-base-dev libjpeg-dev
```

### 2. Virtual environment

```bash
python3 -m venv --system-site-packages venv
source venv/bin/activate
```

`--system-site-packages` is **required**. `picamera2` and `gpiozero` are apt
packages; a normal venv cannot see them and you will get import errors that
look like missing packages when they are installed and sitting right there.

### 3. Swap, before installing dlib

```bash
sudo dphys-swapfile swapoff
sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
sudo dphys-swapfile setup && sudo dphys-swapfile swapon
```

dlib has no ARM wheel. It compiles from source, takes 45–90 minutes, and the
linker will be OOM-killed on a 2 GB Pi without swap. Revert swap afterwards if
you like; SD-card swap shortens card life.

**The shortcut:** put `FACE_BACKEND=lbph` in `.env`, delete the two dlib lines
from `requirements-pi.txt`, and this whole step disappears. LBPH installs in
two minutes and runs far faster. It is meaningfully less accurate — which is a
legitimate trade-off to make and to write up, not a failure.

### 4. Install

```bash
pip install -r requirements-pi.txt
```

### 5. Camera

Ribbon cable: contacts toward the HDMI ports, blue tab toward the USB ports.
Then:

```bash
libcamera-hello --list-cameras
python tools/check_hardware.py
python -m camera.camera_test
```

### 6. Re-enroll faces on the Pi

Encodings are backend-specific and resolution-sensitive. Copying
`face_encodings.pkl` from your laptop will give you bad matches. Enroll again:

```bash
python -m face_auth.face_registration --name "Recipient" --samples 8
```

Enroll at the destination, in the lighting the robot will actually meet.
Corridor lighting differs from your desk lamp far more than you expect.

### 7. Run

```bash
python main.py --simulate                  # wheels and lock still fake
python main.py                             # live hardware
```

---

## Run at boot (optional)

```bash
sudo tee /etc/systemd/system/robot.service > /dev/null << 'EOF'
[Unit]
Description=Secure Delivery Robot
After=multi-user.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/secure-delivery-robot
ExecStart=/home/pi/secure-delivery-robot/venv/bin/python main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now robot.service
journalctl -u robot.service -f
```

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| `No module named picamera2` | venv missing `--system-site-packages` |
| `dlib` build killed | no swap — see step 3 |
| Camera opens, frames are `None` | another process holds it, or the ribbon is reversed |
| Auth fails right after arriving | `MODE_SWITCH_SETTLE_SECONDS` too low |
| Everyone matches everyone | raise `AUTH_MIN_MARGIN`, enroll more varied samples |
| QR never detected | print bigger, 10 cm minimum; check lighting and glare |
| Motors stutter, Pi reboots | brownout — motors need their own battery |
| Solenoid clicks but won't hold | supply can't deliver the coil's inrush current |
| `cv2.imshow` errors on Pi | expected headless; `core/display.py` handles it |
