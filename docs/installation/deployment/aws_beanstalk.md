# AWS Elastic Beanstalk Deployment

CHAOTICA can be deployed on AWS Elastic Beanstalk using the Python platform. This guide covers deploying with RDS PostgreSQL database and optional S3 storage.

## Prerequisites

- AWS CLI configured with appropriate permissions
- EB CLI installed (`pip install awsebcli`)
- Docker (for building application bundle)
- PostgreSQL database (RDS recommended)

## Architecture

The AWS deployment consists of:
- **Elastic Beanstalk Application**: Django application hosting
- **RDS PostgreSQL**: Database service
- **Application Load Balancer**: Traffic distribution
- **Auto Scaling Group**: Automatic scaling based on demand
- **S3 Bucket** (optional): Static and media file storage
- **CloudWatch**: Logging and monitoring

## Deployment Package Structure

Create the following structure for your deployment:
```
chaotica-eb/
├── application.py          # WSGI entry point
├── requirements.txt        # Python dependencies
├── .ebextensions/         # EB configuration
│   ├── django.config
│   ├── python.config
│   └── https-redirect.config
├── .platform/
│   └── hooks/
│       └── postdeploy/
│           └── 01_migrate.sh
└── static/                # Static files (if not using S3)
```

## Configuration Files

### application.py
```python
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chaotica.settings')
application = get_wsgi_application()
```

### requirements.txt
```
Django==5.2.3
psycopg2-binary
gunicorn
boto3
django-storages
# ... other dependencies from app/requirements.txt
```

### .ebextensions/django.config
```yaml
option_settings:
  aws:elasticbeanstalk:container:python:
    WSGIPath: application.py
  aws:elasticbeanstalk:application:environment:
    DJANGO_SETTINGS_MODULE: chaotica.settings
    DJANGO_ENV: Production
    DEBUG: "0"
    PYTHONPATH: "/var/app/current:$PYTHONPATH"
```

### .ebextensions/python.config
```yaml
option_settings:
  aws:elasticbeanstalk:container:python:
    NumProcesses: 3
    NumThreads: 20
  aws:elasticbeanstalk:command:
    Timeout: 3600

commands:
  01_collectstatic:
    command: "source /var/app/venv/staging-LQM1lest/bin/activate && python manage.py collectstatic --noinput"
    leader_only: true
```

### .ebextensions/https-redirect.config
```yaml
Resources:
  AWSEBV2LoadBalancerListener:
    Type: AWS::ElasticLoadBalancingV2::Listener
    Properties:
      DefaultActions:
        - Type: redirect
          RedirectConfig:
            Protocol: HTTPS
            Port: 443
            Host: "#{host}"
            Path: "/#{path}"
            Query: "#{query}"
            StatusCode: HTTP_301
      LoadBalancerArn:
        Ref: AWSEBV2LoadBalancer
      Port: 80
      Protocol: HTTP
```

### .platform/hooks/postdeploy/01_migrate.sh
```bash
#!/bin/bash
source /var/app/venv/*/bin/activate
cd /var/app/current

python manage.py migrate --noinput
python manage.py createcachetable
```

## Environment Variables

Set these in the EB Console or via EB CLI:

### Required Variables
```bash
SECRET_KEY=your-production-secret-key
RDS_DB_NAME=chaotica
RDS_USERNAME=chaotica
RDS_PASSWORD=your-db-password
RDS_HOSTNAME=your-rds-endpoint
RDS_PORT=5432
SQL_ENGINE=django.db.backends.postgresql
```

### Optional Variables
```bash
# S3 Storage
USE_S3=1
AWS_STORAGE_BUCKET_NAME=your-s3-bucket

# Email
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@example.com
EMAIL_HOST_PASSWORD=your-email-password
EMAIL_USE_TLS=True

# Azure AD (Optional)
ADFS_ENABLED=True
ADFS_CLIENT_ID=your-client-id
ADFS_CLIENT_SECRET=your-client-secret
ADFS_TENANT_ID=your-tenant-id

# Site Configuration
SITE_DOMAIN=your-domain.com
SITE_PROTO=https
DJANGO_ALLOWED_HOSTS=your-domain.com *.elasticbeanstalk.com
```

## Deployment Steps

### 1. Initialize EB Application
```bash
eb init chaotica-app
# Select region and platform (Python 3.9 or later)
```

### 2. Create Environment
```bash
eb create chaotica-prod
# This creates the environment with default settings
```

### 3. Configure RDS Database
```bash
# Option 1: Create RDS instance separately (recommended)
aws rds create-db-instance \
  --db-instance-identifier chaotica-db \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --master-username chaotica \
  --master-user-password your-password \
  --allocated-storage 20

# Option 2: Add RDS via EB Console (couples DB to environment)
```

### 4. Set Environment Variables
```bash
eb setenv SECRET_KEY=your-secret-key \
          RDS_HOSTNAME=your-rds-endpoint \
          RDS_PASSWORD=your-db-password \
          # ... other variables
```

### 5. Deploy Application
```bash
eb deploy
```

### 6. Create Superuser
```bash
eb ssh
source /var/app/venv/*/bin/activate
cd /var/app/current
python manage.py createsuperuser
exit
```

## S3 Storage Setup (Optional)

### 1. Create S3 Bucket
```bash
aws s3 mb s3://your-chaotica-bucket
```

### 2. Set Bucket Policy
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::your-chaotica-bucket/static/*"
        }
    ]
}
```

### 3. Configure CORS
```json
[
    {
        "AllowedHeaders": ["*"],
        "AllowedMethods": ["GET", "POST", "PUT"],
        "AllowedOrigins": ["https://your-domain.com"],
        "ExposeHeaders": []
    }
]
```

## Auto Scaling Configuration

### Application Auto Scaling
```yaml
# .ebextensions/autoscaling.config
option_settings:
  aws:autoscaling:asg:
    MinSize: 1
    MaxSize: 10
  aws:autoscaling:trigger:
    MeasureName: CPUUtilization
    Unit: Percent
    UpperThreshold: 70
    LowerThreshold: 20
    ScaleUpIncrement: 2
    ScaleDownIncrement: -1
```

## SSL Certificate

### Using AWS Certificate Manager
1. Request certificate in ACM for your domain
2. Configure Load Balancer to use certificate:

```yaml
# .ebextensions/ssl.config
option_settings:
  aws:elb:listener:443:
    ListenerProtocol: HTTPS
    SSLCertificateId: arn:aws:acm:region:account:certificate/certificate-id
    InstancePort: 80
    InstanceProtocol: HTTP
```

## Monitoring and Logging

### CloudWatch Configuration
```yaml
# .ebextensions/cloudwatch.config
option_settings:
  aws:elasticbeanstalk:cloudwatch:logs:
    StreamLogs: true
    DeleteOnTerminate: false
    RetentionInDays: 7
  aws:elasticbeanstalk:cloudwatch:logs:health:
    HealthStreamingEnabled: true
    DeleteOnTerminate: false
    RetentionInDays: 7
```

### Application Logging
Configure Django logging for CloudWatch:
```python
# In Django settings
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': '/opt/python/log/django.log',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
```

## Maintenance

### Updates
```bash
# Deploy new version
eb deploy

# Check application health
eb health

# View logs
eb logs

# SSH to instance
eb ssh
```

### Database Maintenance
```bash
# Create database backup
eb ssh
pg_dump -h $RDS_HOSTNAME -U $RDS_USERNAME $RDS_DB_NAME > backup.sql

# Restore from backup
psql -h $RDS_HOSTNAME -U $RDS_USERNAME $RDS_DB_NAME < backup.sql
```

## Cost Optimization

1. **Instance Types**: Start with t3.small, scale as needed
2. **Reserved Instances**: For predictable workloads
3. **Scheduled Scaling**: Scale down during off-hours
4. **Database**: Use RDS reserved instances for production
5. **Storage**: Use S3 Standard-IA for backups

## Troubleshooting

### Common Issues

1. **Static Files Not Loading**:
   - Ensure `collectstatic` runs during deployment
   - Check S3 bucket permissions if using S3
   - Verify `STATIC_URL` and `STATIC_ROOT` settings

2. **Database Connection Issues**:
   - Verify RDS security group allows EB security group
   - Check environment variables are set correctly
   - Ensure RDS instance is in same VPC as EB environment

3. **Application Not Starting**:
   - Check EB logs: `eb logs`
   - Verify `application.py` is in root directory
   - Check Python dependencies in `requirements.txt`

4. **502 Bad Gateway**:
   - Usually indicates application startup failure
   - Check Django settings and database connectivity
   - Review EB event logs in AWS Console

### Logs Locations
- Application logs: `/opt/python/log/`
- Web server logs: `/var/log/nginx/`
- EB platform logs: Available via `eb logs` command

## Production Checklist

- [ ] Change default `SECRET_KEY`
- [ ] Use external RDS database (not tied to EB environment)
- [ ] Configure SSL certificate
- [ ] Set up CloudWatch monitoring
- [ ] Configure log retention
- [ ] Set up database backups
- [ ] Configure auto-scaling policies
- [ ] Test disaster recovery procedures
- [ ] Set up health checks and alarms
- [ ] Use S3 for static/media files storage

