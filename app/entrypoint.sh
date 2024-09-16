#!/bin/sh

cd /app 
env > /run/chaotica.env

if [ "$DATABASE" = "postgres" ]
then
    echo "Waiting for postgres..."

    while ! nc -z $SQL_HOST $SQL_PORT; do
      sleep 0.1
    done

    echo "PostgreSQL started"
fi

sudo -Eu chaotica -- python3 manage.py migrate --noinput
# sudo -Eu chaotica -- python3 manage.py collectstatic --noinput
sudo -Eu chaotica -- /usr/bin/crontab /crontab.txt

exec "$@"