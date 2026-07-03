# KnockBlock

A phone-controlled office status sign. Tap a button on your phone; the status
instantly shows on a 64x32 HUB75 LED matrix driven by a Raspberry Pi 4.

## Features

- **Status presets** with emoji icons (On a Call, Free, In a Meeting, Do Not
  Disturb), rendered with auto-fitted text on the panel
- **Custom messages** — type anything (leading emoji becomes the icon), pick a
  background color; recent messages become one-tap chips
- **Auto-revert timers** — "On a Call for 30 min, then back to Free," with a
  live countdown; survives restarts
- **Live preview** — the phone UI mirrors exactly what the panel shows
- **After-hours weather** — outside working hours, an idle sign shows current
  temp + today's high/low (Open-Meteo, no API key; location auto-detected
  from the Pi's public IP, overridable via settings lat/lon)
- **Brightness control**, **state persistence** across power cycles, and a
  **PWA** phone UI (Add to Home Screen for a full-screen app)

## API

Everything the UI does goes through JSON endpoints, so you can script it:

- `GET /api/state` — current status, brightness, message, recents, settings,
  weather
- `POST /api/state` — any subset of:
  `{"status": "free" | "on_a_call" | ... | "off"}`,
  `{"message": {"text": "...", "color": "blue"}}`,
  `{"brightness": 5-100}`, `{"revert_minutes": N}` (with a status/message),
  `{"settings": {"weather_idle": true, "work_start": "08:00",
  "work_end": "18:00", "units": "f", "lat": null, "lon": null}}`
- `GET /preview.png` — PNG of what the panel currently shows

## Hardware

- Raspberry Pi 4 Model B
- Waveshare 64x32 HUB75 RGB LED matrix panel
- Generic HUB75 adapter board plugged into the 40-pin GPIO header (no HAT
  level-shifter IC)
- A separate 5V power supply for the panel, rated for at least 4A. **Do not**
  power the panel from the Pi's 5V pins — a 64x32 panel at full brightness can
  draw more current than the Pi can safely supply, and both will brown out.

## Project layout

- `app.py` — Flask web server; exposes the phone UI and a `/set_status/<name>` endpoint
- `matrix.py` — wraps `rpi-rgb-led-matrix` to render a preset (text + colors) to the panel
- `presets.py` — the status screens (label, text lines, colors) shown as phone buttons
- `templates/index.html` — the phone UI
- `hello_matrix.py` — standalone smoke test, no Flask required
- `requirements.txt` — Python deps installed via pip (Flask, Pillow)

## Setup, step by step

### 1. Disable onboard audio

The Pi's onboard audio uses the same PWM hardware the LED matrix needs for
clean timing; leaving it enabled causes flicker and ghosting.

Edit the boot config (`/boot/firmware/config.txt` on newer Raspberry Pi OS,
or `/boot/config.txt` on older releases) and comment out or remove the audio
line:

```
# dtparam=audio=on
```

**This requires a reboot** (`sudo reboot`) to take effect.

### 2. Install the driver (hzeller/rpi-rgb-led-matrix)

Current Raspberry Pi OS (Debian trixie) blocks system-wide `pip install`
(PEP 668), so everything Python-related lives in a virtualenv inside the
project folder:

```bash
sudo apt-get update
sudo apt-get install -y git python3-dev python3-pip cython3
git clone https://github.com/hzeller/rpi-rgb-led-matrix.git ~/rpi-rgb-led-matrix
cd ~/KnockBlock
python3 -m venv venv
./venv/bin/pip install --upgrade pip
```

The current version of the driver builds via `pyproject.toml`/CMake and
needs Pillow's internal `Imaging.h` C header, which isn't vendored in the
repo. Install Pillow first, then fetch the matching header (and its own
few includes) into the bindings' `shims/` folder before building:

```bash
./venv/bin/pip install Pillow Flask
PILLOW_VERSION=$(./venv/bin/python3 -c "import PIL; print(PIL.__version__)")
cd ~/rpi-rgb-led-matrix/bindings/python/rgbmatrix/shims
for f in Imaging.h ImPlatform.h Mode.h Arrow.h ImagingUtils.h; do
  curl -sSL -o "$f" "https://raw.githubusercontent.com/python-pillow/Pillow/$PILLOW_VERSION/src/libImaging/$f"
done
cd ~/KnockBlock
./venv/bin/pip install ~/rpi-rgb-led-matrix
```

### 3. Install remaining Python deps

Flask and Pillow already went into the venv above (needed there for the
driver's header check); nothing else is required for `requirements.txt`.

### 4. Confirm the driver imports

```bash
./venv/bin/python3 -c "import rgbmatrix; print('ok')"
```

If this fails, the Python bindings didn't build/install correctly — re-run
step 2 and check the build output.

### 5. Light up a static test screen

Before touching the web app, isolate hardware issues with the standalone
test script. It needs `sudo` for GPIO access:

```bash
sudo ./venv/bin/python3 hello_matrix.py
```

You should see "HELLO" / "KNOCKBLOCK" in green text on the panel.

### 6. Hardware troubleshooting

If the test screen is blank, garbled, flickery, or has wrong colors, adjust
these options in `matrix.py` one at a time and re-run `hello_matrix.py`:

| Symptom | Try |
| --- | --- |
| Panel is completely blank | Check the panel's own power supply is on and wired to the panel (not just the Pi); confirm the ribbon cable orientation; try `hardware_mapping = "adafruit-hat"` if your adapter board has a level-shifter chip |
| Image is garbled / scrambled pixels | Increase `gpio_slowdown` (try 2, then 3, then 4) — the Pi is driving the GPIO faster than the panel can latch |
| Flickering or dim/ghosting rows | Increase `gpio_slowdown`; confirm onboard audio is disabled (step 1) |
| Colors are swapped (e.g. red/blue flipped) | Change `led_rgb_sequence` from `"RGB"` to `"RBG"`, `"GRB"`, etc. until colors match |

### 7. Run the web app

```bash
sudo ./venv/bin/python3 app.py
```

Find the Pi's IP address with `hostname -I`, then on your phone (same WiFi),
visit `http://<pi-ip-address>:5000`. Tapping a button should update the panel
immediately.

### 8. Auto-start on boot (systemd)

Create `/etc/systemd/system/knockblock.service` (adjust `WorkingDirectory` and
`User` if your project lives somewhere other than `/home/ahein/KnockBlock`):

```ini
[Unit]
Description=KnockBlock status sign
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/ahein/KnockBlock
ExecStart=/home/ahein/KnockBlock/venv/bin/python3 /home/ahein/KnockBlock/app.py
Restart=on-failure
User=root

[Install]
WantedBy=multi-user.target
```

The service runs as `root` because the LED matrix library needs raw GPIO
access, same as the `sudo` used above.

Enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable knockblock
sudo systemctl start knockblock
```

Check status and logs:

```bash
sudo systemctl status knockblock
sudo journalctl -u knockblock -f
```
