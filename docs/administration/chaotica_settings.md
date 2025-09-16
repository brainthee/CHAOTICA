# Application Settings

CHAOTICA provides extensive configuration options through environment variables and runtime settings. This guide covers both deployment-time configuration and runtime administrative settings.

## Environment Variables

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `0` | Enable Django debug mode (set to `1` for debugging) |
| `SECRET_KEY` | *(default provided)* | Django secret key - **MUST change in production** |
| `DJANGO_ENV` | `Dev` | Environment type (Dev/Production) |
| `MAINTENANCE_MODE` | `0` | Enable maintenance mode (set to `1` to enable) |
| `DJANGO_ALLOWED_HOSTS` | `* web` | Allowed host headers (space-separated) |
| `SITE_DOMAIN` | `127.0.0.1:8000` | Domain for the site |
| `SITE_PROTO` | `http` | Protocol (http/https) |

### Database Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SQL_ENGINE` | *(SQLite)* | Database engine (`django.db.backends.postgresql`) |
| `RDS_DB_NAME` | - | Database name |
| `RDS_USERNAME` | - | Database username |
| `RDS_PASSWORD` | - | Database password |
| `RDS_HOSTNAME` | - | Database hostname |
| `RDS_PORT` | `5432` | Database port |

### Authentication (ADFS/OAuth2)

| Variable | Default | Description |
|----------|---------|-------------|
| `ADFS_CLIENT_ID` | - | Azure AD Client ID |
| `ADFS_CLIENT_SECRET` | - | Azure AD Client Secret |
| `ADFS_TENANT_ID` | - | Azure AD Tenant ID |

### Email Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `EMAIL_BACKEND` | `console` | Email backend (use `smtp.EmailBackend` for SMTP) |
| `EMAIL_HOST` | `localhost` | SMTP server hostname |
| `EMAIL_HOST_USER` | - | SMTP username |
| `EMAIL_HOST_PASSWORD` | - | SMTP password |
| `EMAIL_PORT` | `25` | SMTP port |
| `EMAIL_USE_TLS` | `True` | Enable TLS |
| `EMAIL_USE_SSL` | `False` | Enable SSL |
| `DEFAULT_FROM_EMAIL` | `CHAOTICA <notifications@chaotica.app>` | Default sender email |

### Storage (AWS S3)

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_S3` | `0` | Use S3 for static/media files (set to `1`) |
| `AWS_STORAGE_ACCESS_KEY_ID` | - | AWS Access Key |
| `AWS_STORAGE_SECRET_ACCESS_KEY` | - | AWS Secret Key |
| `AWS_STORAGE_BUCKET_NAME` | - | S3 bucket name |

### Monitoring

| Variable | Default | Description |
|----------|---------|-------------|
| `SENTRY_BACKEND_DSN` | - | Sentry DSN for backend error tracking |
| `SENTRY_FRONTEND_DSN` | - | Sentry DSN for frontend error tracking |

### Security

| Variable | Default | Description |
|----------|---------|-------------|
| `CSRF_COOKIE_SECURE` | `True` (non-dev) | Secure CSRF cookies |
| `SESSION_COOKIE_SECURE` | `True` (non-dev) | Secure session cookies |
| `SESSION_COOKIE_AGE` | `43200` (12h) | Session timeout in seconds |
| `SESSION_EXPIRE_AT_BROWSER_CLOSE` | `True` | Expire sessions on browser close |

### GeoIP

| Variable | Default | Description |
|----------|---------|-------------|
| `MAXMIND_LICENSE_KEY` | - | MaxMind license key for GeoIP |
| `GEOIP_PATH` | `/tmp/geoip` | Path to GeoIP database files |

## Runtime Configuration Settings

CHAOTICA uses Django Constance for runtime configuration. These settings can be modified through the Django admin interface at `/admin/constance/config/`.

### Feature Flags

| Setting | Default | Description |
|---------|---------|-------------|
| `EMAIL_ENABLED` | `False` | Enable email notifications |
| `ADFS_ENABLED` | `False` | Enable ADFS/Azure AD authentication |
| `ADFS_AUTO_LOGIN` | `False` | Automatically redirect to ADFS login |
| `REGISTRATION_ENABLED` | `True` | Allow user self-registration |
| `LOCAL_LOGIN_ENABLED` | `True` | Allow local username/password login |
| `INVITE_ENABLED` | `True` | Allow user invitations |

### Support Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `SUPPORT_DOC_URL` | `https://docs.chaotica.app/en/latest/` | Documentation URL |
| `SUPPORT_MAILBOX` | GitHub Issues URL | Support contact URL |
| `SUPPORT_ISSUES` | GitHub Issues URL | Bug report URL |

### Workflow Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `JOB_ID_START` | `2500` | Starting number for Job IDs |
| `PROJECT_ID_START` | `9000` | Starting number for Project IDs |
| `DAYS_TO_TQA` | `0` | Days after testing for TQA deadline |
| `DAYS_TO_PQA` | `5` | Days after testing for PQA deadline |
| `DAYS_TO_DELIVERY` | `7` | Days after testing for delivery deadline |

### Work Schedule Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `DEFAULT_HOURS_IN_DAY` | `7.5` | Standard work hours per day |
| `DEFAULT_WORKING_DAYS` | `[1,2,3,4,5]` | Working days (0=Sunday, 1=Monday...) |
| `LEAVE_DAYS_NOTICE` | `14` | Required notice days for leave requests |
| `LEAVE_ENFORCE_LIMIT` | `False` | Enforce leave balance limits |

### Notification Timing

| Setting | Default | Description |
|---------|---------|-------------|
| `PRECHECK_LATE_HOURS` | `24` | Hours between precheck late notifications |
| `TQA_LATE_HOURS` | `24` | Hours between TQA late notifications |
| `PQA_LATE_HOURS` | `24` | Hours between PQA late notifications |
| `DELIVERY_LATE_HOURS` | `24` | Hours between delivery late notifications |

### User Management

| Setting | Default | Description |
|---------|---------|-------------|
| `USER_INVITE_EXPIRY` | `7` | Days until user invitations expire |
| `SKILLS_REVIEW_DAYS` | `31` | Days between skills review prompts |
| `PROFILE_REVIEW_DAYS` | `182` | Days between profile review prompts |

### Appearance & UI

| Setting | Default | Description |
|---------|---------|-------------|
| `SNOW_ENABLED` | `False` | Enable snow animation (seasonal) |
| `KONAMI_ENABLED` | `True` | Enable Konami code easter egg |
| `SITE_NOTICE_ENABLED` | `False` | Show site-wide notice banner |
| `SITE_NOTICE_MSG` | - | Site notice message text |
| `SITE_NOTICE_COLOUR` | `primary` | Bootstrap color class for notice |

### Schedule Colors

| Setting | Default | Description |
|---------|---------|-------------|
| `SCHEDULE_COLOR_AVAILABLE` | `#8BC34A` | Color for available schedule slots |
| `SCHEDULE_COLOR_UNAVAILABLE` | `#F44336` | Color for unavailable schedule slots |

## Accessing Settings

### Environment Variables
Environment variables are set at deployment time:
- Docker: Set in `docker-compose.yml` or via `-e` flags
- Kubernetes: Set via ConfigMaps or Secrets
- Development: Use `.env` file in the app directory

### Runtime Settings
Access runtime settings via Django admin:
1. Navigate to `/admin/`
2. Go to "Constance" → "Config"
3. Modify settings as needed
4. Changes take effect immediately

### Command Line
Some settings can be managed via Django management commands:
```bash
python manage.py download_geoip_db  # Download GeoIP database
```

## Security Considerations

- Always change `SECRET_KEY` in production
- Use strong passwords for database connections
- Enable HTTPS in production (`SITE_PROTO=https`)
- Set secure cookie flags for production
- Use proper firewall rules and network security
- Regularly update GeoIP databases
- Monitor with Sentry in production environments

