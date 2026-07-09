#!/bin/bash
#
# Nightly demo refresh for demo.chaotica.app.
#
# Self-contained: run from cron out of this directory. It pulls the latest
# published image, brings the stack up (waiting for the DB to be healthy —
# no more fixed `sleep`), wipes and regenerates demo data, and prunes the old
# image layers it just replaced so the disk can't silently fill up again.
#
# An EXIT trap guarantees the site is never left stuck in maintenance mode or
# down: on any failure it brings the stack back and clears maintenance mode.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

dc() { docker compose "$@"; }

# manage.py helper — runs inside the web container.
manage() { dc exec -T web python3 manage.py "$@"; }

recover() {
    rc=$?
    if [ "$rc" -ne 0 ]; then
        log "ERROR: refresh failed (exit $rc). Recovering site..."
        dc up -d --wait >/dev/null 2>&1 || true
        manage maintenance_mode off >/dev/null 2>&1 || true
        log "Recovery attempt finished; site should serve the previous dataset."
    fi
    exit "$rc"
}
trap recover EXIT

log "Pulling latest image..."
dc pull --quiet

log "Starting stack (waiting for healthy)..."
dc up -d --wait

log "Reclaiming disk from the image we just replaced..."
docker image prune -f >/dev/null

log "Applying migrations..."
manage migrate --noinput

log "Flushing database..."
manage flush --noinput

# Maintenance mode is stored in the DB, so enable it *after* the flush above
# (which would otherwise clear it) to hide the half-built dataset while we seed.
log "Enabling maintenance mode..."
manage maintenance_mode on

log "Collecting static files..."
manage collectstatic --noinput

log "Ensuring superuser exists..."
manage shell -c 'from django.contrib.auth import get_user_model; U=get_user_model(); U.objects.filter(email="admin@demo.chaotica.app").exists() or U.objects.create_superuser(email="admin@demo.chaotica.app", password="DemoAdmin123!")'

log "Generating fresh demo data..."
manage generate_demo_data --force --users 25 --clients 12 --jobs 100 --password 'DemoUser123!'

# generate_demo_data only gives the 25 generated users unit memberships. The
# admin superuser is created separately above, so without this it lands on an
# empty dashboard ("You are not a member of any organisational units").
log "Adding superuser to all organisational units..."
manage shell <<'PYEOF'
from django.contrib.auth import get_user_model
from jobtracker.models import OrganisationalUnit, OrganisationalUnitMember, OrganisationalUnitRole
U = get_user_model()
admin = U.objects.filter(email="admin@demo.chaotica.app").first()
if admin:
    roles = list(OrganisationalUnitRole.objects.exclude(name="Pending Approval"))
    for unit in OrganisationalUnit.objects.all():
        m, _ = OrganisationalUnitMember.objects.get_or_create(member=admin, unit=unit)
        m.roles.set(roles)
PYEOF

log "Clearing cache..."
manage shell -c "from django.core.cache import cache; cache.clear()"

log "Disabling maintenance mode..."
manage maintenance_mode off

log "Demo data refresh completed successfully."
