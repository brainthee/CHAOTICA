# Quickstart

The fastest way to get CHAOTICA up and running is with Docker.

## Quick Demo

You can quickly and easily run CHAOTICA by using Docker:

```bash
docker run -p 8000:8000 -e DEBUG=1 brainthee/chaotica
```

When finished, you should be able to view it at `http://localhost:8000`. When you first visit the site, it will ask you to register a new account. This first account will automatically be given full administrative permissions.

!!! Warning
    Beware - this will run with SQLite as the database and without persistent volumes. You will lose data if that container is destroyed!

## Production Setup

For a more robust setup with persistent data, use Docker Compose:

```bash
cd deploy/docker-compose
docker-compose up
```

This will start:
- CHAOTICA application
- PostgreSQL database
- Redis for caching
- Nginx reverse proxy

Access the application at `http://localhost:1338`.

## Development Setup

For local development:

```bash
cd app
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

See the [installation documentation](installation/deployment/docker.md) for more detailed setup instructions.