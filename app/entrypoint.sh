#!/bin/bash

cd /app 

# Initialize ClamAV
echo "Initializing ClamAV..."
mkdir -p /var/log/clamav /var/lib/clamav /var/run/clamav
chown -R root:root /var/log/clamav /var/lib/clamav /var/run/clamav

# Check if virus database exists, if not download it
if [ ! -f /var/lib/clamav/main.cvd ] && [ ! -f /var/lib/clamav/main.cld ]; then
    echo "Downloading initial ClamAV virus database..."
    freshclam --config-file=/etc/clamav/freshclam.conf
fi

# Lets write the DB CA to disk if it exists
if [[ -n ${RDS_TLS_USE} ]]; then
  if [[ -n ${RDS_TLS_URL} ]]; then
    CA_CERT_PATH="/app/rds-ca-cert.pem"
    if curl -s -o $CA_CERT_PATH $RDS_TLS_URL; then
        export RDS_TLS_CA_PATH="$CA_CERT_PATH"
    else
        echo "Error: Failed to download certificate"
    fi
  elif [[ -n ${RDS_TLS_CA} ]]; then   
    CA_CERT_PATH="/app/ca-cert.pem"
    if echo "$RDS_TLS_CA" | base64 -d > "$CA_CERT_PATH"; then
        export RDS_TLS_CA_PATH="$CA_CERT_PATH"
    else
        echo "Error: Failed to decode base64 certificate"
    fi
  else
    echo "Warning: RDS_TLS_USE set but no CA defined"
  fi
fi

env > /run/chaotica.env

if [ "$DATABASE" = "postgres" ]
then
    echo "Waiting for postgres..."

    while ! nc -z $SQL_HOST $SQL_PORT; do
      sleep 0.1
    done

    echo "PostgreSQL started"
fi

if [ "$USE_REDIS" = "true" ]; then
    echo "Starting Redis and waiting for it to be ready..."
    redis-server --daemonize yes
    while ! redis-cli ping > /dev/null 2>&1; do
        echo "Waiting for Redis..."
        sleep 1
    done
    redis-cli shutdown
    echo "Redis is ready"
fi

sudo -Eu chaotica -- python3 manage.py download_geoip_db
sudo -Eu chaotica -- python3 manage.py migrate --noinput
if [ "$RUN_COLLECTSTATIC" = "true" ]; then
    echo "Running collectstatic..."
    sudo -Eu chaotica -- python3 manage.py collectstatic --noinput
fi
sudo -Eu chaotica -- /usr/bin/crontab /crontab.txt

exec "$@"