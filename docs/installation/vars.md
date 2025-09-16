# Environment Variables

CHAOTICA uses environment variables for configuration. These can be set in Docker Compose, Kubernetes ConfigMaps/Secrets, or as system environment variables.

## Required Variables

These variables must be set for production deployments:

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | Django secret key - **MUST change in production** | `your-super-secret-key-here` |
| `RDS_PASSWORD` | Database password | `secure-db-password` |

## Django Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `0` | Enable Django debug mode (set to `1` for development) |
| `MAINTENANCE_MODE` | `0` | Enable maintenance mode |
| `SECRET_KEY` | *(insecure default)* | Django secret key |
| `DJANGO_ENV` | `Dev` | Environment type (`Dev`/`Production`) |
| `DJANGO_VERSION` | `bleeding-edge` | Version identifier for deployment |
| `DJANGO_ALLOWED_HOSTS` | `* web` | Space-separated list of allowed hostnames |
| `USE_X_FORWARDED_HOST` | `True` | Trust X-Forwarded-Host header |
| `SITE_DOMAIN` | `127.0.0.1:8000` | Primary domain for the application |
| `SITE_PROTO` | `http` | Protocol (`http`/`https`) |

## Security Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `CSRF_COOKIE_SECURE` | `True` (prod) | Secure CSRF cookies (HTTPS only) |
| `SESSION_COOKIE_SECURE` | `True` (prod) | Secure session cookies (HTTPS only) |
| `SESSION_EXPIRE_AT_BROWSER_CLOSE` | `True` | Sessions expire when browser closes |
| `SESSION_COOKIE_AGE` | `43200` | Session timeout in seconds (12 hours) |

## Database Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SQL_ENGINE` | *(SQLite)* | Database backend (`django.db.backends.postgresql`) |
| `RDS_DB_NAME` | - | Database name |
| `RDS_USERNAME` | - | Database username |
| `RDS_PASSWORD` | - | Database password |
| `RDS_HOSTNAME` | - | Database hostname |
| `RDS_PORT` | `5432` | Database port |

## Authentication (Azure AD/ADFS)

| Variable | Default | Description |
|----------|---------|-------------|
| `ADFS_CLIENT_ID` | - | Azure AD Application (client) ID |
| `ADFS_CLIENT_SECRET` | - | Azure AD Client secret |
| `ADFS_TENANT_ID` | - | Azure AD Directory (tenant) ID |

## Email Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `EMAIL_BACKEND` | `console` | Email backend (use `django.core.mail.backends.smtp.EmailBackend`) |
| `EMAIL_HOST` | `localhost` | SMTP server hostname |
| `EMAIL_HOST_USER` | - | SMTP username |
| `EMAIL_HOST_PASSWORD` | - | SMTP password |
| `EMAIL_PORT` | `25` | SMTP port (587 for TLS, 465 for SSL) |
| `EMAIL_USE_SSL` | `False` | Enable SSL connection |
| `EMAIL_USE_TLS` | `True` | Enable TLS connection |
| `DEFAULT_FROM_EMAIL` | `CHAOTICA <notifications@chaotica.app>` | Default sender email |

## Twilio (SMS) Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `TWILIO_ACC` | - | Twilio Account SID |
| `TWILIO_TOKEN` | - | Twilio Auth Token |
| `TWILIO_SERVICESID` | - | Twilio Service SID |

## Monitoring & Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `SENTRY_BACKEND_DSN` | - | Sentry DSN for backend error tracking |
| `SENTRY_FRONTEND_DSN` | - | Sentry DSN for frontend error tracking |

## Application Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_HOURS_IN_DAY` | `7.5` | Default working hours per day |
| `TZ` | - | System timezone (e.g., `Europe/London`, `America/New_York`) |

## GeoIP Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `MAXMIND_LICENSE_KEY` | - | MaxMind license key for GeoIP database |
| `GEOIP_PATH` | `/tmp/geoip` | Path to store GeoIP database files |

## AWS S3 Storage (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_S3` | `0` | Enable S3 for static/media files (set to `1`) |
| `AWS_STORAGE_ACCESS_KEY_ID` | - | AWS Access Key ID |
| `AWS_STORAGE_SECRET_ACCESS_KEY` | - | AWS Secret Access Key |
| `AWS_STORAGE_BUCKET_NAME` | - | S3 bucket name |

## Example Configurations

### Development (.env file)
```bash
DEBUG=1
SECRET_KEY=dev-key-not-for-production
DJANGO_ENV=Dev
```

### Production (Docker Compose)
```yaml
environment:
  - DEBUG=0
  - SECRET_KEY=your-production-secret-key
  - DJANGO_ENV=Production
  - SQL_ENGINE=django.db.backends.postgresql
  - RDS_DB_NAME=chaotica
  - RDS_USERNAME=chaotica_user
  - RDS_PASSWORD=secure-password
  - RDS_HOSTNAME=db
  - EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
  - EMAIL_HOST=smtp.example.com
  - EMAIL_PORT=587
  - EMAIL_USE_TLS=True
```

### Kubernetes (ConfigMap/Secret)
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: chaotica-config
data:
  DEBUG: "0"
  DJANGO_ENV: "Production"
  SQL_ENGINE: "django.db.backends.postgresql"
  # ... other non-sensitive config
---
apiVersion: v1
kind: Secret
metadata:
  name: chaotica-secrets
data:
  SECRET_KEY: <base64-encoded-secret>
  RDS_PASSWORD: <base64-encoded-password>
  # ... other sensitive data
```