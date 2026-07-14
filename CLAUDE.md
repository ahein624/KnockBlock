# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A phone-controlled LED status sign ("AH.knockblock"): a Flask app on a
Raspberry Pi 4 drives a 64×32 HUB75 panel; a single-file vanilla-JS PWA
(`templates/index.html`) controls it. **The production sign is exposed to
the public internet** (via Cloudflare → a reverse proxy on the LAN → the
Pi), so every new endpoint must decide its auth story deliberately.

## Development

No hardware needed — a stubbed panel driver lives in `dev/`:

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python3 dev/dev_server.py          # http://127.0.0.1:5099, password: devpassword1
```

Runtime files go to `dev/state/` (gitignored); a real sign's `auth.json` /
`state.json` are never touched. Env switches: `KNOCKBLOCK_DEV_FRESH=1`
(wipe state), `KNOCKBLOCK_DEV_LOCAL=1` (browser counts as LAN),
`KNOCKBLOCK_DEV_UNCLAIMED=1` (exercise the first-run claim wizard).
The harness deliberately marks `127.0.0.1` as an untrusted proxy so the
login/demo flows behave like they do for a public client — plain curl
gets a 401; log in first or combine with `DEV_LOCAL`.

There is no test suite. Verify by driving the dev server (curl the JSON
API, exercise the UI) — helpers for simulating a public client: send an
`X-Forwarded-For` header. Shell scripts (`install.sh`,
`scripts/update.sh`) must pass `shellcheck`; `install.sh --dry-run`
prints its plan. `scripts/update.sh` is testable against a throwaway
clone with `KNOCKBLOCK_NO_SYSTEMD=1` and `KNOCKBLOCK_HEALTH_URL=…`.

## Architecture

**One process, one lock.** `app.py` holds a global `state` dict guarded by
`lock`, persisted atomically to `state.json` (`_save_state`). Anything
that mutates state — including `_arbitrate`, which clears expired holds
as a side effect — must run under `lock`.

**The arbiter decides what shows.** `_arbitrate(now)` picks the winning
source in fixed priority: `manual → oncall → focus → calendar → schedule
→ idle`. A 1s scheduler thread (`_scheduler_loop`) calls
`_render_current`, which re-arbitrates, computes a render signature, and
skips no-op repaints — that signature diff is why the 1s tick is cheap.
Timed things (hold TTLs, focus timers, schedule windows, the on-call
watchdog) are all timestamps checked on each arbitration; there are no
`threading.Timer`s. Status transitions are logged to monthly JSONL files
by `history.py` (`_record_transition`); custom message text is
deliberately never logged.

**State keys follow the `_load_state` pattern.** Any new persisted key
needs: a default (in `DEFAULT_SETTINGS` or the `state` literal),
validation in `_load_state` (drop garbage silently, never crash on an old
file), and validation in the `POST /api/state` handler. Schedules show
the pattern end to end (`_valid_schedule` shared by both).

**Auth has four tiers** (see `_require_auth` and `_is_local_request`):
LAN bypass (every check must agree: private source IP, no proxy headers,
source not in `auth.json` `untrusted_proxies`, host ≠ `public_host`) →
session cookie → API token → demo mode (read-only; writes get a quip from
`DEMO_QUIPS`; new payload fields need a redaction decision in
`_api_payload`). Privileged endpoints (`/api/token`, `/api/update*`) are
**session-or-local only** — a leaked API token must never mint tokens or
swap code. The first-run claim wizard (`/setup`) only exists while no
password is set and only answers LAN clients; `--set-password` is the
only reset path.

**Rendering pipeline.** `matrix.py` composes 64×32 PIL images
(works anywhere) and drives the panel via the `rgbmatrix` C extension
(Pi only; `MatrixDisplay`). Animated statuses (uploads/GIFs via
`media.frames_from_bytes`, procedural `fire_frames` and `arcade_frames`)
loop in matrix.py's animation thread through `play_frames`; the phone
preview at `/preview.png` snapshots whatever the panel shows. New
animated screens follow the arcade pattern: generate deterministic frames
once, cache, add a status to the three allowlists (`_load_state`,
`POST /api/state`, `quick_set`) plus a signature/play branch in
`_render_current`.

**The UI is one file.** `templates/index.html`: vanilla JS, 5s polling of
`/api/state`, optimistic updates reconciled against the response, no
build step, no dependencies beyond Google Fonts. Themes are CSS-variable
blocks on `[data-theme=…]`, chosen per device via the `kb_theme` cookie
which `index()` reads to stamp `<html data-theme>` server-side (no
flash). Workshop is the default; semantic roles: `--tan` = primary
action, `--orange` = active/now, `--radius` = corner physics.

## Deployment

The Pi is a **git clone of `main`** that updates itself: merge to `main`,
then Settings → Software → "Update sign" (or `POST /api/update`). The
updater (`scripts/update.sh`, run as a transient systemd unit) fetches a
pinned `origin/main`, resets, restarts, health-checks, and **rolls back**
on failure — so merging to `main` is deploying. Untracked runtime files
(`auth.json`, `state.json`, `media/`, `history-*.jsonl`,
`update_status.json`) survive updates by being gitignored; keep it that
way. PWA icons (`static/*.png`) are generated on-device by
`make_icons.py` and are NOT deployed by updates. The service runs as root
(GPIO needs it); root git requires the system-level `safe.directory`
entry that `install.sh` adds. Fresh installs: `install.sh` (idempotent,
also the manual upgrade path).

## Voice and design

Copy is dry and deadpan — "practical over decorative", sentence case,
no exclamation marks, no emoji decoration in UI chrome. The default
"Workshop" look is warm Bitter/Barlow on brown (`#221A12`); orange means
"active right now" and nothing else. Fun features (dumpster fire, arcade)
use **original procedural art only** — no licensed sprites or memes.
