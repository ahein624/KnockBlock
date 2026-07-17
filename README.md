# AH.knockblock

A phone-controlled office status sign. Tap a button on your phone; the status
instantly shows on a 64x32 HUB75 LED matrix driven by a Raspberry Pi 4.

## Quick start

On a fresh Raspberry Pi with the panel wired up (see [Hardware](#hardware)):

```bash
curl -sSL https://raw.githubusercontent.com/ahein624/KnockBlock/main/install.sh | bash
```

The installer clones the code, builds the panel driver, and installs the
`knockblock` systemd service (it may ask you to reboot once for the audio
change, then re-run). When it finishes, open `http://<pi-ip>:5000` from a
phone on the same WiFi to **claim your sign**: set a password, name it, and
you're live. Re-running the installer later is the upgrade path — it never
touches your password, state, or uploaded media.

Prefer to see every step, or debugging a panel? The full walkthrough is in
[Manual setup](#setup-step-by-step).

## Features

- **Status presets** with emoji icons (On a Call, Free, In a Meeting, Do Not
  Disturb), rendered with auto-fitted text on the panel
- **Custom messages** — type anything (leading emoji becomes the icon), pick a
  background color; recent messages become one-tap chips
- **Custom statuses** — build your own status buttons (up to 8): text over
  a panel color, or over an uploaded image/meme/GIF — captioned, or with
  the caption switched off so the GIF plays bare (the text then just names
  the button). They join the status grid with real-render thumbnails, work
  from the Stream Deck (`/api/set/cs_…`), and deleting one that's showing
  releases to auto
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
- **Themes** — per-device, in Settings → Appearance: *Glass* (dark,
  translucent, modern), *Workshop* (the warm house style), or *Clear*
  (high-contrast, plain, accessibility-first). Stored in a cookie the
  server reads, so pages load in your theme with no flash
- **Panel styles** — sign-wide, in Settings → Panel style: *Classic* flat
  cards, *Nameplate* (skeuomorphic brushed-metal shop plates — beveled
  edges, corner screws, engraved text, a glowing indicator lamp in the
  status color), *Terminal* (green-phosphor console with scanlines), or
  *8-bit* (pixel icon cards — headset, sun, meeting heads, do-not-enter —
  with the clock and focus screens drawn to match: sun or moon by hour,
  hourglass timer). All original art; the status buttons preview whichever
  is active
- **Password login** — everything (UI and API) requires either a logged-in
  browser session or the API token, so the sign can be exposed beyond the LAN
- **API token for scripts** — one-URL status changes from a Stream Deck,
  Apple Shortcuts, or curl (see below)
- **Sleep schedule** — the panel goes dark during a configurable window
  (e.g. 22:00–07:00) whenever it's idle; a deliberately set status or custom
  message still shows. Or pick **Moonlight** instead of dark: a very dim
  night scene — crescent moon, twinkling stars, and a sleeping cat
  exhaling z's
- **On-a-call autodetect** — a tiny agent on your laptop watches the
  camera/mic (macOS via OverSight, Windows via the ConsentStore registry)
  and heartbeats the sign; a 15s watchdog clears the status if the agent
  dies mid-call
- **Focus timer** — 15/25/50-minute buttons; the panel shows FOCUS with a
  live MM:SS countdown, then releases automatically
- **Calendar** — point it at a Google Calendar secret iCal address (no
  OAuth) and the sign shows "In a Meeting" during events, recurring ones
  included
- **GIFs & images** — search Tenor/Giphy and pick from a grid of results,
  or hit Roll for a random one; picks work as panel screens and as custom
  status backgrounds, and you can upload any image or animated GIF from the
  phone. Media rides the manual-hold rules, so the hold TTL and timer chips
  keep a joke from becoming your all-day status. Picked results only ever
  download from the providers' own CDNs. The old public demo keys have gone
  stale, so put a personal (free) key in `auth.json`:
  `{"giphy_key": "..."}` — it's tried first
- **Screen designer** — a pixel editor for the 64×32 panel right in the
  phone UI: draw, flood-fill, undo, start from what the sign is showing,
  save favorites on the device, and send to the panel (rides the same
  manual-hold rules as uploads)
- **Dumpster fire mode** — one tap plays an original procedurally-animated
  "THIS IS FINE." flame scene (no meme copyright, works offline); also at
  `/api/set/dumpster_fire` for a Stream Deck panic button
- **Arcade mode** — an original retro-platformer loop drawn pixel by pixel:
  scrolling bricks, pipes, blinking coins, and a little runner in KnockBlock
  orange who jumps the pipes (no licensed sprites, works offline); also at
  `/api/set/arcade`
- **Demo mode** — share `/demo` and visitors watch the real sign live
  (state, preview, countdowns) but every write is refused with a polite
  quip; secrets (calendar URL, location, API token) are redacted and the
  settings sheet is hidden. Logging in normally exits demo mode
- **Scheduled statuses** — recurring rules like "Lunch, 12:00–13:00,
  Mon–Fri" the sign follows on its own; presets, the clock, or a custom
  message, overnight windows included. A manual tap overrides; Auto resumes
- **Weekly insights** — a "This week" panel with time spent in meetings,
  calls, and focus, from an append-only local history (three months kept,
  message text never logged)
- **First-run claim wizard** — a fresh sign is claimed from a phone on its
  own WiFi: password, name, work hours, API token. No SSH needed
- **Self-update** — an "Update sign" button pulls the latest code, restarts,
  and rolls itself back if the sign doesn't come back up
- **Priority arbiter** — when several sources are active at once:
  manual hold → on-call → focus → calendar → schedule → idle. Manual
  presses release after a configurable TTL (default 2h) so a tapped button
  can't suppress autodetect all day; the Auto button releases a hold early

## Login & security

A fresh sign is **claimed** from its own network: open `http://<pi-ip>:5000`
from a phone on the sign's WiFi and the first-run wizard asks for a
password, a name, and your work hours. The wizard only answers LAN clients
and only while no password exists, so an internet-exposed unclaimed sign
still can't be seized by a stranger. From a terminal (also the only way to
*reset* a forgotten password):

```bash
sudo ./venv/bin/python3 app.py --set-password
```

Claiming also reveals the **API token** used by scripted clients
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

## Remote access

The recommended way to reach the sign away from home is **Tailscale** — no
port forwarding, no reverse proxy, no exposed attack surface:

1. On the Pi: `curl -fsSL https://tailscale.com/install.sh | sh`, then
   `sudo tailscale up`.
2. Install the Tailscale app on your phone and sign in to the same tailnet.
3. Visit `http://<pi-tailscale-name>:5000` (MagicDNS) from anywhere. For
   HTTPS — which lets the phone use the clipboard API and installs more
   cleanly as a PWA — run `sudo tailscale serve --bg 5000` and use the
   `https://…ts.net` URL it prints.

One deliberate quirk: Tailscale addresses live in `100.64.0.0/10`, which is
*not* a private range, so tailnet clients are asked for the password like
any other remote visitor. That's the safe default — anyone you share your
tailnet with shouldn't automatically control your door.

The advanced alternative — a public domain through a reverse proxy or
Cloudflare tunnel — works with the `public_host` / `untrusted_proxies` keys
above; that's how the original sign runs. WiFi captive-portal provisioning
(configuring the Pi's WiFi from the phone) is future work; for now the Pi
joins WiFi the usual way (Raspberry Pi Imager presets or `nmtui`).

## API

Everything the UI does goes through JSON endpoints, so you can script it.
Authenticate with `Authorization: Bearer <token>`, an `X-Api-Token` header,
or `?token=<token>`:

- `GET /api/state` — what's showing and why (`status`, `source`, `held`),
  plus brightness, recents, focus/calendar state, schedules, settings,
  weather
- `POST /api/state` — any subset of:
  `{"status": "free" | "on_a_call" | ... | "clock" | "auto"}` (`auto`
  releases a manual hold),
  `{"message": {"text": "...", "color": "blue"}}`,
  `{"focus_minutes": 25}` (0 cancels),
  `{"brightness": 5-100}`, `{"revert_minutes": N}` (with a status/message),
  `{"settings": {"sign_name": "Knockblock", "weather_idle": true,
  "work_start": "08:00", "work_end": "18:00", "units": "f", "lat": null,
  "lon": null, "sleep_enabled": true, "sleep_start": "22:00",
  "sleep_end": "07:00", "ical_url": "https://…",
  "manual_ttl_minutes": 120}}`,
  `{"schedules": [{"label": "Lunch", "status": "custom",
  "message": {"text": "Back at 1", "color": "orange"}, "start": "12:00",
  "end": "13:00", "days": [0,1,2,3,4], "enabled": true}]}` — full-list
  replace; `status` is a preset key, `"clock"`, or `"custom"` (which
  requires `message`); `start > end` spans midnight; first matching rule
  wins
- `GET /api/insights?days=7` — seconds per status per local day plus
  totals, from the on-device history (max 31 days; blocked in demo mode)
- `POST /api/statuses` — create a custom status (multipart: `text`, and
  `bg_color` or an image/GIF `file`); `DELETE /api/statuses/<id>` removes
  one (releasing the sign if it's showing). Set them like any status:
  `{"status": "cs_…"}` or `/api/set/cs_…`
- `POST /api/oncall` — `{"active": true|false}` heartbeat from a laptop
  sensor; the status clears itself 15s after the last `true`
- `GET /api/gif/search?q=…` — GIF candidates: `[{"url", "preview", "title"}]`
- `POST /api/gif` — `{"url": "...", "title": "..."}` shows a search pick
  (provider CDNs only), or `{"query": "dancing cat"}` for a random one;
  `revert_minutes` optional on both
- `POST /api/upload` — multipart `file` (image or GIF) plus optional
  `revert_minutes`; shows it on the panel
- `GET|POST /api/set/<status>` — one-URL change for buttons:
  `/api/set/on_a_call?minutes=30`, `/api/set/focus?minutes=25`,
  `/api/set/dumpster_fire`, `/api/set/auto`
- `POST /api/update` / `GET /api/update/status` — start the self-updater /
  watch its progress. Session or LAN only, like `GET|POST /api/token` —
  a leaked API token can't swap code or read credentials
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

## Updating

Settings → Software → **Update sign** pulls the latest code, restarts the
service, and health-checks itself — if the sign doesn't come back up it
rolls back to the version that worked and says so. Under the hood it's
`scripts/update.sh` run as a transient systemd unit; your password, state,
history, and uploaded media are untracked files the update never touches.
Re-running `install.sh` does the same job from a shell.

## Project layout

- `app.py` — Flask web server; exposes the phone UI and the JSON API
- `auth.py` — password + API-token auth, backed by `auth.json` (not in git)
- `matrix.py` — wraps `rpi-rgb-led-matrix` to render a preset (text + colors) to the panel
- `presets.py` — the status screens (label, text lines, colors) shown as phone buttons
- `history.py` — append-only status history + the insights aggregation
- `templates/` — the phone UI, login, and first-run claim wizard
- `install.sh` / `deploy/` — one-command installer and the systemd unit
- `scripts/update.sh` — the self-updater (fetch, swap, health-check, roll back)
- `hello_matrix.py` — standalone smoke test, no Flask required
- `requirements.txt` — Python deps installed via pip (Flask, Pillow)
- `dev/` — hardware-free dev server (stubbed panel) for UI work

## Development (no hardware needed)

Everything except the physical panel runs on any machine:

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python3 dev/dev_server.py
```

Open http://127.0.0.1:5099 and log in with `devpassword1`. Runtime files
live in `dev/state/` (gitignored), so a real sign's `auth.json` and
`state.json` are never touched. The dev server poses as a public client
so the login and demo flows are exercisable; see the switches documented
at the top of `dev/dev_server.py` (`KNOCKBLOCK_DEV_LOCAL`,
`KNOCKBLOCK_DEV_UNCLAIMED`, `KNOCKBLOCK_DEV_FRESH`).

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

## Future work

- **WiFi captive-portal provisioning** — claim a sign that isn't on WiFi
  yet, straight from the phone; today the Pi joins WiFi via the Raspberry
  Pi Imager presets or `nmtui`
- **Tailnet-as-local option** — an opt-in `trusted_networks` key so tailnet
  clients skip the password like LAN clients do
- **Drag-to-reorder schedules** — priority is list order; today it's
  up-arrows

---

*Practical over decorative.*
