#!/usr/bin/env bash
# Self-update for KnockBlock. Launched by POST /api/update as a transient
# systemd unit so it survives the app restart it performs. Progress goes to
# update_status.json for GET /api/update/status to relay.
#
# Untracked files (auth.json, state.json, media/, history) are never touched
# by the reset. On a failed health check it rolls back to the previous SHA.
#
# Test switches: KNOCKBLOCK_NO_SYSTEMD=1 skips the service restart;
# KNOCKBLOCK_HEALTH_URL overrides the post-restart health check target.
set -uo pipefail

# Everything lives in main() so bash parses the whole file before running —
# the reset below replaces this very script mid-run otherwise.
main() {
  REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  STATUS_FILE="$REPO_DIR/update_status.json"
  HEALTH_URL="${KNOCKBLOCK_HEALTH_URL:-http://127.0.0.1:5000/api/state}"
  REF="origin/main"  # pinned: the request never chooses what to run
  OLD_SHA="$(git -C "$REPO_DIR" rev-parse HEAD)"
  NEW_SHA=""

  status fetching
  if ! git -C "$REPO_DIR" fetch --quiet origin main; then
    status failed '"git fetch failed — is the Pi online?"'
    exit 1
  fi
  NEW_SHA="$(git -C "$REPO_DIR" rev-parse "$REF")"
  if [[ "$NEW_SHA" == "$OLD_SHA" ]]; then
    status "done"
    exit 0
  fi

  status installing
  if ! git -C "$REPO_DIR" reset --hard --quiet "$NEW_SHA"; then
    status failed '"git reset failed"'
    exit 1
  fi
  if ! git -C "$REPO_DIR" diff --quiet "$OLD_SHA" "$NEW_SHA" -- requirements.txt; then
    if ! "$REPO_DIR/venv/bin/pip" install -q -r "$REPO_DIR/requirements.txt"; then
      rollback '"dependency install failed"'
      exit 1
    fi
  fi

  status restarting
  restart_service
  if healthy; then
    status "done"
  else
    rollback '"the updated sign did not come back up"'
    exit 1
  fi
}

status() { # phase [json-quoted error]
  printf '{"phase":"%s","from":"%s","to":"%s","error":%s,"ts":%s}\n' \
    "$1" "$OLD_SHA" "$NEW_SHA" "${2:-null}" "$(date +%s)" > "$STATUS_FILE.tmp"
  mv "$STATUS_FILE.tmp" "$STATUS_FILE"
}

restart_service() {
  [[ -n "${KNOCKBLOCK_NO_SYSTEMD:-}" ]] || systemctl restart knockblock
}

healthy() {
  for _ in $(seq 1 15); do
    sleep 2
    curl -sf --max-time 3 "$HEALTH_URL" >/dev/null && return 0
  done
  return 1
}

rollback() {
  git -C "$REPO_DIR" reset --hard --quiet "$OLD_SHA"
  "$REPO_DIR/venv/bin/pip" install -q -r "$REPO_DIR/requirements.txt" || true
  restart_service
  status rolled_back "$1"
}

main "$@"
