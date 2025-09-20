#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
APP_DIR="$PROJECT_ROOT/app"
LOG_FILE="$PROJECT_ROOT/chaotica-demo-refresh.log"

# Activate virtual environment if it exists
if [ -f "$PROJECT_ROOT/venv/bin/activate" ]; then
    source "$PROJECT_ROOT/venv/bin/activate"
fi

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "Starting CHAOTICA demo data refresh"

cd "$APP_DIR"

log "Running database migrations..."
python3 manage.py migrate --noinput

log "Collecting static files..."
python3 manage.py collectstatic --noinput

log "Creating superuser if not exists..."
echo "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.filter(email='admin@chaotica-demo.com').exists() or User.objects.create_superuser('admin@chaotica-demo.com', 'DemoAdmin123!')" | python3 manage.py shell

log "Clearing existing demo data..."
python3 manage.py generate_demo_data --clear

log "Generating fresh demo data..."
python3 manage.py generate_demo_data --users 25 --clients 12 --jobs 100

log "Creating demo notification subscriptions..."
echo "
from django.contrib.auth import get_user_model
from notifications.models import NotificationSubscription, NotificationRule
User = get_user_model()

for user in User.objects.filter(is_superuser=False)[:10]:
    try:
        sub, created = NotificationSubscription.objects.get_or_create(
            user=user,
            defaults={'email': user.email, 'is_active': True}
        )
        if created:
            print(f'Created subscription for {user.email}')
    except Exception as e:
        print(f'Error creating subscription for {user.email}: {e}')
" | python3 manage.py shell

log "Clearing cache..."
echo "from django.core.cache import cache; cache.clear()" | python3 manage.py shell

if command -v systemctl &> /dev/null && systemctl is-active --quiet celery; then
    log "Restarting Celery workers..."
    sudo systemctl restart celery celerybeat
fi

if command -v systemctl &> /dev/null && systemctl is-active --quiet gunicorn; then
    log "Restarting application server..."
    sudo systemctl restart gunicorn
fi

log "Demo data refresh completed successfully!"

exit 0