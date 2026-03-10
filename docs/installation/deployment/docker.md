# Docker Deployment

CHAOTICA can be deployed using Docker in several ways, from a simple single container for testing to a full production setup with Docker Compose.

## Single Container (Development/Testing)

For quick testing or development:

```bash
docker run -p 8000:8000 -e DEBUG=1 brainthee/chaotica:latest
```

This will:
- Run CHAOTICA on port 8000
- Use SQLite database (data will be lost when container stops)
- Enable Django debug mode

## Production Deployment with Docker Compose

For production deployments, use the provided Docker Compose configuration:

### Prerequisites

- Docker
- Docker Compose

### Setup

1. Clone the repository and navigate to the Docker Compose directory:
```bash
git clone <repository-url>
cd CHAOTICA/deploy/docker-compose
```

2. Review and modify the `docker-compose.yml` file:

```yaml
# Key environment variables to customize:
- SECRET_KEY=CHANGE_ME          # Change this!
- RDS_PASSWORD=Hunter2          # Change this!
- DEBUG=0                       # Set to 1 for debug mode
- TZ=Europe/London             # Your timezone
```

3. Start the services:
```bash
docker-compose up -d
```

### Services Included

The Docker Compose setup includes:

- **web**: CHAOTICA Django application
- **db**: PostgreSQL 15 database
- **nginx**: Reverse proxy and static file serving

### Access

- Application: `http://localhost:1338`
- Admin interface: `http://localhost:1338/admin/`

### Configuration

#### Database
- PostgreSQL is used by default
- Data is persisted in a Docker volume
- Connection details are configured via environment variables

#### Static Files
- Served by nginx
- Shared between containers via volumes

#### Email (Optional)
Configure email settings by uncommenting and setting:
```yaml
- EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
- EMAIL_HOST=your.smtp.server
- EMAIL_PORT=587
- EMAIL_HOST_USER=your@email.com
- EMAIL_HOST_PASSWORD=yourpassword
```

#### S3 Storage (Optional)
For AWS S3 static/media file storage:
```yaml
- USE_S3=1
- AWS_STORAGE_ACCESS_KEY_ID=your_key
- AWS_STORAGE_SECRET_ACCESS_KEY=your_secret
- AWS_STORAGE_BUCKET_NAME=your_bucket
```

### First-time Setup

After starting the containers:

1. Create a superuser account:
```bash
docker-compose exec web python manage.py createsuperuser
```

2. Load initial data (if available):
```bash
docker-compose exec web python manage.py loaddata initial_data
```

### Updating

To update CHAOTICA:

```bash
docker-compose pull
docker-compose up -d
```

### Backups

Database backups can be created using:
```bash
docker-compose exec db pg_dump -U chaotica chaotica > backup.sql
```

### Troubleshooting

- Check logs: `docker-compose logs`
- Check individual service logs: `docker-compose logs web`
- Restart services: `docker-compose restart`
- Rebuild containers: `docker-compose up --build`

