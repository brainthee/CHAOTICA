#!/usr/bin/env bash
#
# Nightly FULL rebuild of the public demo (demo.chaotica.app).
#
# Destroys the whole stack *including volumes* (database, media, static) and
# builds it again from the latest published image: the entrypoint migrates a
# brand-new database, then generate_demo_data seeds it and creates the
# advertised demo login. Run by chaotica-demo-reset.timer (systemd); output
# goes to the journal: `journalctl -u chaotica-demo-reset`.
#
# While it runs, nginx serves a maintenance page (flag file), so visitors never
# see a half-seeded site — or the fresh-install setup wizard, which an empty
# database would otherwise expose to anyone.
#
# On failure the maintenance page is deliberately LEFT UP (an empty database is
# not safe to expose) and the unit exits non-zero, so `systemctl --failed`
# shows it.

set -euo pipefail

cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"

set -a
# shellcheck source=/dev/null
. ./.env
set +a

FLAG=maintenance/on

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
dc() { docker compose "$@"; }
manage() { dc exec -T web python3 manage.py "$@"; }

on_exit() {
    rc=$?
    if [ "$rc" -ne 0 ]; then
        log "ERROR: reset failed (exit $rc). Leaving the maintenance page up."
        touch "$FLAG"
        dc up -d nginx >/dev/null 2>&1 || true
    fi
    exit "$rc"
}
trap on_exit EXIT

log "Pulling images..."
# A registry blip shouldn't cost a night's reset: fall back to cached images.
dc pull --quiet --ignore-pull-failures

log "Maintenance page on."
touch "$FLAG"

log "Tearing down stack and ALL data volumes..."
dc down --volumes --remove-orphans

log "Starting nginx (maintenance page)..."
dc up -d nginx

log "Starting app on a fresh database (migrations run in the entrypoint)..."
dc up -d --wait --wait-timeout "${DEMO_STARTUP_TIMEOUT:-2400}" web

log "Seeding demo data..."
manage generate_demo_data --force \
    --users "${DEMO_SEED_USERS:-25}" \
    --clients "${DEMO_SEED_CLIENTS:-12}" \
    --jobs "${DEMO_SEED_JOBS:-100}" \
    --password "$DEMO_USER_PASSWORD" \
    --admin-email "$DEMO_USER" \
    --admin-password "$DEMO_PASS"

log "Verifying the advertised demo login..."
manage shell -c "
import os, sys
from django.contrib.auth import get_user_model
u = get_user_model().objects.filter(email=os.environ['DEMO_USER']).first()
sys.exit(0 if u and u.is_active and u.check_password(os.environ['DEMO_PASS']) else 1)
"

log "Maintenance page off."
rm -f "$FLAG"

log "Smoke-testing through nginx..."
body=$(mktemp)
code=$(curl -s -o "$body" -w '%{http_code}' \
    -H "Host: ${SITE_DOMAIN:-localhost}" -H 'X-Forwarded-Proto: https' \
    http://127.0.0.1/auth/login/)
if [ "$code" != "200" ] || ! grep -qF "value=\"$DEMO_USER\"" "$body"; then
    log "Login page check failed: HTTP $code, demo login pre-filled: $(grep -cF "$DEMO_USER" "$body")."
    rm -f "$body"
    exit 1
fi
rm -f "$body"

log "Pruning superseded images..."
docker image prune -f >/dev/null

log "Demo reset completed successfully."
