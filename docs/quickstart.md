# Quickstart

The fastest way to get CHAOTICA up and running is with Docker.

## Quick Demo

You can quickly and easily run CHAOTICA by using Docker:

```bash
docker run -p 8000:8000 -e DEBUG=1 brainthee/chaotica
```

When finished, you should be able to view it at `http://localhost:8000`. When you first visit the site, the **setup wizard** will guide you through creating the first account, which is automatically given full administrative permissions, along with your first organisational unit, services, skills and clients.

!!! Note "Setup wizard access"
    The setup wizard only runs on a fresh install — that is, while there are **no user accounts yet**. As soon as the first administrator exists, the wizard is restricted to logged-in administrators (superusers) and the rest of the application becomes available. Having no clients or services is a normal state and will **not** re-trigger the wizard.

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

### Demo data

To populate a development database with realistic sample data (users, clients, jobs, phases, scheduled timeslots and leave), use the `generate_demo_data` management command:

```bash
cd app
python manage.py generate_demo_data            # default dataset
python manage.py generate_demo_data --minimal  # small dataset for quick testing
python manage.py generate_demo_data --clear    # clear existing demo data, then regenerate
```

Options: `--users`, `--clients` and `--jobs` control how much data is created; `--minimal` creates a small dataset; `--clear` wipes previously generated data before regenerating (built-in reference data such as the standard timeslot types is preserved). Demo users are created with the password `DemoPass123!`.

!!! Warning
    `generate_demo_data` is intended for development/demo environments only — do not run it against a production database.

See the [installation documentation](installation/deployment/docker.md) for more detailed setup instructions.