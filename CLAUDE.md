# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CHAOTICA is a Django-based engagement lifecycle management tool primarily designed for security testing teams. It stands for **C**entralised **H**ub for **A**ssigning **O**perational **T**asks, **I**nteractive **C**alendaring and **A**lerts.

## Development Commands

### Django Management
- `cd app && python manage.py runserver` - Start development server
- `cd app && python manage.py migrate` - Apply database migrations
- `cd app && python manage.py makemigrations` - Create new migrations
- `cd app && python manage.py collectstatic` - Collect static files
- `cd app && python manage.py test` - Run test suite
- `cd app && python manage.py createsuperuser` - Create admin user
- `cd app && python manage.py download_geoip_db` - Download GeoIP database

### Database Management
- `cd app && ./scripts/cleanMigrations.sh` - Clean migrations and SQLite database (development only)
- The script removes db.sqlite3, deletes migration files, and runs makemigrations

### Docker Development
- `cd deploy/docker-compose && docker-compose up` - Start full stack with PostgreSQL, Redis, and Nginx
- Default access: http://localhost:1338
- Database runs on PostgreSQL in production, SQLite for local development

### Documentation
- `mkdocs serve` - Serve documentation locally (requires docs/requirements.txt)
- `mkdocs build` - Build documentation
- Documentation uses MkDocs with Material theme and mkdocstrings for API docs

## Architecture

### Django Applications
The project is structured as a multi-app Django project:

- **chaotica/** - Main project settings and root URL configuration
- **dashboard/** - Main dashboard views and functionality
- **jobtracker/** - Core engagement/job tracking functionality
- **reporting/** - Reporting and analytics features
- **notifications/** - Notification system with rules and subscriptions
- **chaotica_utils/** - Shared utilities and common functionality
- **rm_sync/** - Risk management synchronization
- **virtualpet/** - Additional feature module

### Key Technical Components
- **Django 5.2.3** with PostgreSQL/SQLite database support
- **Celery 5.5.3** for background task processing
- **Redis** for caching and Celery broker
- **Django REST Framework** for API endpoints
- **ClamAV** integration for file scanning
- **Sentry** integration for error tracking
- **ADFS/OAuth2** authentication support
- **Bootstrap 5** with Crispy Forms for UI

### Settings & Configuration
- Main settings in `app/chaotica/settings.py`
- Environment variables used for configuration (see docker-compose.yml)
- Supports multiple environments (Dev/Production) via `DJANGO_ENV`
- Database, email, authentication, and storage can be configured via environment variables

### URL Structure
URLs are organized hierarchically:
- `/` redirects to `/dashboard/`
- `/admin/` - Django admin interface
- `/dashboard/` - Main dashboard
- `/reporting/` - Reports and analytics
- `/notifications/` - Notification management
- `/jobtracker/` - Job/engagement tracking
- `/rm_sync/` - Risk management sync
- `/oauth2/` - ADFS authentication

### File Structure
- `app/` - Main Django application code
- `app/static/` - Static assets (CSS, JS, images)
- `app/staticfiles/` - Collected static files
- `app/templates/` - Django templates
- `app/media/` - User-uploaded files
- `deploy/` - Docker and deployment configurations
- `docs/` - MkDocs documentation source

### Testing
- Test files follow Django convention: `tests.py` in each app
- Run tests with `python manage.py test` from the app directory
- Uses Django's built-in TestCase framework

## Dependencies

Python dependencies are managed in `app/requirements.txt`. Key packages include:
- Django and Django extensions (auth-adfs, REST framework, etc.)
- Celery for background tasks
- Database connectors (psycopg2, mysqlclient)
- AWS SDK (boto3) for S3 integration
- Reporting libraries (pandas, openpyxl)
- Security tools (django-clamav)