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
- **Clock & weather screen** — a tappable mode showing the local time plus
  current conditions; outside working hours an idle sign switches to it
  automatically (Open-Meteo, no API key; location auto-detected from the
  Pi's public IP, overridable via settings lat/lon; time follows the Pi's
  system timezone)
- **Brightness control**, **state persistence** across power cycles, and a
  **PWA** phone UI (Add to Home Screen for a full-screen app)
- **Password login** — everything (UI and API) requires either a logged-in
  browser session or the API token, so the sign can be exposed beyond the LAN
- **API token for scripts** — one-URL status changes from a Stream Deck,
  Apple Shortcuts, or curl (see below)
- **Sleep schedule** — the panel goes dark during a configurable window
  (e.g. 22:00–07:00) whenever it's idle; a deliberately set status or custom
  message still shows
- **On-a-call autodetect** — a tiny agent on your laptop watches the
  camera/mic (macOS via OverSight, Windows via the ConsentStore registry)
  and heartbeats the sign; a 15s watchdog clears the status if the agent
  dies mid-call
- **Focus timer** — 15/25/50-minute buttons; the panel shows FOCUS with a
  live MM:SS countdown, then releases automatically
- **Calendar** — point it at a Google Calendar secret iCal address (no
  OAuth) and the sign shows "In a Meeting" during events, recurring ones
  included
- **Priority arbiter** — when several sources are active at once:
  manual hold → on-call → focus → calendar → idle. Manual presses release
  after a configurable TTL (default 2h) so a tapped button can't suppress
  autodetect all day; the Auto button releases a hold early

## Login & security

The password is set from the shell, never through the web (so an exposed,
not-yet-configured sign can't be claimed by a stranger):

```bash
sudo ./venv/bin/python3 app.py --set-password
```

This also prints the **API token** used by scripted clients
(`--show-token` reprints it; the phone UI shows it too, with a regenerate
button). Logins get a long-lived session cookie — right for a personal PWA.
Repeated failed logins back off with a per-IP lockout.

**LAN clients skip the password entirely.** A request counts as local only
when every check agrees: the TCP source address is private, no forwarding
headers (`X-Forwarded-For`, `X-Real-IP`, `CF-*`) are present, the source
isn't a known reverse proxy, and the request isn't addressed to the public
hostname. Public traffic that reaches the sign through a proxy on the same
LAN therefore still needs the password. Two optional keys in `auth.json`
configure the site-specific parts:

```json
{"public_host": "sign.example.com", "untrusted_proxies": ["192.168.1.5"]}
```

Set `untrusted_proxies` to the LAN address(es) of whatever relays outside
traffic to the sign (reverse proxy, tunnel daemon), and `public_host` to the
domain it serves.

If you expose the sign to the internet, put it behind HTTPS (a reverse proxy
like Caddy, or a Cloudflare tunnel) — over plain HTTP the password and token
travel in the clear. A Tailscale/VPN-only setup avoids the exposure entirely.

## API

Everything the UI does goes through JSON endpoints, so you can script it.
Authenticate with `Authorization: Bearer <token>`, an `X-Api-Token` header,
or `?token=<token>`:

- `GET /api/state` — what's showing and why (`status`, `source`, `held`),
  plus brightness, recents, focus/calendar state, settings, weather
- `POST /api/state` — any subset of:
  `{"status": "free" | "on_a_call" | ... | "clock" | "auto"}` (`auto`
  releases a manual hold),
  `{"message": {"text": "...", "color": "blue"}}`,
  `{"focus_minutes": 25}` (0 cancels),
  `{"brightness": 5-100}`, `{"revert_minutes": N}` (with a status/message),
  `{"settings": {"weather_idle": true, "work_start": "08:00",
  "work_end": "18:00", "units": "f", "lat": null, "lon": null,
  "sleep_enabled": true, "sleep_start": "22:00", "sleep_end": "07:00",
  "ical_url": "https://…", "manual_ttl_minutes": 120}}`
- `POST /api/oncall` — `{"active": true|false}` heartbeat from a laptop
  sensor; the status clears itself 15s after the last `true`
- `GET|POST /api/set/<status>` — one-URL change for buttons:
  `/api/set/on_a_call?minutes=30`, `/api/set/focus?minutes=25`,
  `/api/set/auto`
- `GET /preview.png` — PNG of what the panel currently shows

## On-call laptop sensors

Both agents heartbeat `POST /api/oncall` every 5s while the camera or mic
is in use, so a crashed agent just times out after 15s.

**macOS** — install [OverSight](https://objective-see.org/products/oversight.html),
then in OverSight's settings set *Execute Action* to
`agents/oversight-knockblock.sh` (copy it anywhere) and enable *pass
arguments*. Edit the script's `SIGN_URL`/`TOKEN` lines or export
`KNOCKBLOCK_URL`/`KNOCKBLOCK_TOKEN`.

**Windows** — run `agents/knockblock-sensor.ps1` at logon (see the
`schtasks` one-liner in the script header). It polls the same registry keys
Windows uses for the camera/mic tray indicators.

Neither agent needs the token while the laptop is on the sign's LAN, but
set it anyway so the buttons keep working from anywhere.

## Stream Deck

Any Stream Deck action that can hit a URL works — no custom plugin needed.
With the stock **System → Website** action (or the "API Ninja" / "Web
Requests" plugins if you'd rather POST without opening a browser), point a
button at:

```
http://<sign-host>:5000/api/set/on_a_call?token=<your-token>
```

Add `&minutes=30` for "On a Call for 30 minutes, then back to Free". The
same URLs work from Apple Shortcuts ("Get Contents of URL") or cron.

## Hardware

- Raspberry Pi 4 Model B
- Waveshare 64x32 HUB75 RGB LED matrix panel
- Generic HUB75 adapter board plugged into the 40-pin GPIO header (no HAT
  level-shifter IC)
- A separate 5V power supply for the panel, rated for at least 4A. **Do not**
  power the panel from the Pi's 5V pins — a 64x32 panel at full brightness can
  draw more current than the Pi can safely supply, and both will brown out.

## Project layout

- `app.py` — Flask web server; exposes the phone UI and the JSON API
- `auth.py` — password + API-token auth, backed by `auth.json` (not in git)
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

### 7. Set the login password

```bash
sudo ./venv/bin/python3 app.py --set-password
```

Note the API token it prints if you plan to script the sign.

### 8. Run the web app

```bash
sudo ./venv/bin/python3 app.py
```

Find the Pi's IP address with `hostname -I`, then on your phone (same WiFi),
visit `http://<pi-ip-address>:5000`, log in, and tap a button — the panel
should update immediately.

### 9. Auto-start on boot (systemd)

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
