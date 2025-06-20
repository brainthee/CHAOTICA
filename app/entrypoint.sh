#!/bin/bash

cd /app 

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

sudo -Eu chaotica -- python3 manage.py download_geoip_db
sudo -Eu chaotica -- python3 manage.py migrate --noinput
sudo -Eu chaotica -- python3 manage.py collectstatic --noinput
sudo -Eu chaotica -- /usr/bin/crontab /crontab.txt

exec "$@"