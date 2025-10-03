#!/bin/bash

set -e

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "Starting CHAOTICA demo data refresh in Docker environment"

log "Killing database..."
docker compose exec -T web python3 manage.py flush --noinput

log "Running database migrations..."
docker compose exec -T web python3 manage.py migrate --noinput

log "Enabling maintenance mode..."
docker compose exec -T web python3 manage.py maintenance_mode on

log "Collecting static files..."
docker compose exec -T web python3 manage.py collectstatic --noinput

log "Creating superuser if not exists..."
docker compose exec -T web python3 manage.py shell -c 'from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.filter(email="admin@demo.chaotica.app").exists() or User.objects.create_superuser(email="admin@demo.chaotica.app", password="DemoAdmin123!")'

log "Generating fresh data..."
docker compose exec -T web python3 manage.py generate_demo_data --users 25 --clients 12 --jobs 100

log "Clearing cache..."
docker compose exec -T web python3 manage.py shell -c "from django.core.cache import cache; cache.clear()"

log "Restarting web service..."
docker compose restart web

log "Disabling maintenance mode..."
docker compose exec -T web python3 manage.py maintenance_mode off

log "Demo data refresh completed successfully!"

exit 0