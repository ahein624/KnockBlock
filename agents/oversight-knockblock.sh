#!/bin/sh
# KnockBlock on-call sensor for macOS, driven by OverSight
# (https://objective-see.org/products/oversight.html).
#
# Setup: OverSight → Settings → "Execute Action" → point it at this script
# and enable "pass arguments". OverSight then runs it as:
#   oversight-knockblock.sh -device camera|microphone -event on|off
#
# While any device is in use, a background loop heartbeats the sign every
# 5s; the sign clears the status 15s after the last beat (watchdog), so a
# crashed loop can't leave the sign stuck on "On a Call".
#
# Configure via environment or by editing the two lines below.
SIGN_URL="${KNOCKBLOCK_URL:-http://192.168.68.250:5000}"
TOKEN="${KNOCKBLOCK_TOKEN:-}"

STATE_DIR="${TMPDIR:-/tmp}/knockblock-sensor"
PIDFILE="$STATE_DIR/heartbeat.pid"
mkdir -p "$STATE_DIR"

device=""
event=""
while [ $# -gt 0 ]; do
  case "$1" in
    -device) device="$2"; shift 2 ;;
    -event)  event="$2"; shift 2 ;;
    *) shift ;;
  esac
done
[ -n "$device" ] || exit 0

post() {
  curl -s -m 4 -X POST "$SIGN_URL/api/oncall" \
    -H "Content-Type: application/json" \
    ${TOKEN:+-H "X-Api-Token: $TOKEN"} \
    -d "{\"active\": $1}" >/dev/null 2>&1
}

# One flag file per in-use device; a call is "on" while any flag exists,
# so the camera turning off mid-call (audio-only) doesn't end it.
case "$event" in
  on)  touch "$STATE_DIR/$device" ;;
  off) rm -f "$STATE_DIR/$device" ;;
esac

any_active() {
  [ -n "$(find "$STATE_DIR" -type f ! -name heartbeat.pid 2>/dev/null | head -1)" ]
}

if any_active; then
  if [ ! -f "$PIDFILE" ] || ! kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null; then
    (
      while [ -n "$(find "$STATE_DIR" -type f ! -name heartbeat.pid 2>/dev/null | head -1)" ]; do
        post true
        sleep 5
      done
      rm -f "$PIDFILE"
    ) &
    echo $! > "$PIDFILE"
  fi
else
  post false
fi
