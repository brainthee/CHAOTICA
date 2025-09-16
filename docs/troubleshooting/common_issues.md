# Common Issues and Troubleshooting

This comprehensive troubleshooting guide addresses the most frequently encountered issues in CHAOTICA, providing step-by-step solutions and preventive measures.

## Login and Authentication Issues

### Unable to Login

**Symptoms**:
- Login page displays but credentials don't work
- Error messages about invalid username/password
- Redirected back to login page after attempting to login

**Common Causes and Solutions**:

1. **Incorrect Credentials**
   ```
   Solution:
   - Verify username and password are correct
   - Check for caps lock or typing errors
   - Try password reset if available
   ```

2. **Account Locked or Disabled**
   ```
   Solution:
   - Contact administrator to check account status
   - Review account lockout policies
   - Wait for automatic unlock period if applicable
   ```

3. **Database Connection Issues**
   ```
   Diagnosis:
   python manage.py shell
   from django.contrib.auth.models import User
   User.objects.count()  # Should return number of users
   
   Solution:
   - Check database connectivity
   - Verify database credentials in settings
   - Restart database service if needed
   ```

### Azure AD/ADFS Authentication Problems

**ADFS Redirect Loop**:
```
Symptoms: Continuous redirects between CHAOTICA and ADFS
Diagnosis: Check browser developer tools network tab
Solution:
1. Verify ADFS configuration matches CHAOTICA settings
2. Check redirect URIs are correctly configured
3. Ensure system clocks are synchronized
4. Validate SSL certificates on both systems
```

**Token Validation Errors**:
```
Error: "Invalid token signature"
Solution:
1. Check certificate configuration in ADFS
2. Verify token signing certificate hasn't expired
3. Ensure certificate thumbprint matches configuration
4. Restart ADFS service after certificate changes
```

## Performance Issues

### Slow Page Loading

**Symptoms**:
- Pages take more than 5-10 seconds to load
- Timeouts when accessing certain features
- Unresponsive interface elements

**Diagnostic Steps**:
```bash
# Check system resources
htop                    # CPU and memory usage
df -h                  # Disk space
iostat -x 1 5         # Disk I/O performance
netstat -an           # Network connections
```

**Common Solutions**:

1. **Database Performance**
   ```sql
   -- Check slow queries (PostgreSQL)
   SELECT query, calls, total_time, mean_time 
   FROM pg_stat_statements 
   ORDER BY total_time DESC LIMIT 10;
   
   -- Check database connections
   SELECT count(*) FROM pg_stat_activity;
   ```

2. **Memory Issues**
   ```bash
   # Check Django memory usage
   python manage.py check --deploy
   
   # Monitor memory with specific focus on Django processes
   ps aux | grep python | awk '{print $2, $4, $6, $11}'
   ```

3. **Cache Configuration**
   ```python
   # Verify cache backend in settings.py
   CACHES = {
       'default': {
           'BACKEND': 'django.core.cache.backends.redis.RedisCache',
           'LOCATION': 'redis://127.0.0.1:6379/1',
       }
   }
   
   # Test cache functionality
   from django.core.cache import cache
   cache.set('test_key', 'test_value', 30)
   print(cache.get('test_key'))  # Should return 'test_value'
   ```

### High CPU Usage

**Diagnosis**:
```bash
# Identify CPU-intensive processes
top -p $(pgrep -d',' python)

# Check for infinite loops or heavy operations
strace -p <python_process_id> -c

# Monitor Django process performance
python manage.py shell
import psutil
for p in psutil.process_iter(['pid', 'name', 'cpu_percent']):
    if 'python' in p.info['name']:
        print(p.info)
```

**Solutions**:
1. Check for inefficient database queries
2. Review background task processing (Celery)
3. Optimize report generation and data processing
4. Consider scaling horizontally with load balancing

## Database Issues

### Connection Errors

**Error**: "Unable to connect to database"

**Diagnosis and Solutions**:
```bash
# Test database connectivity
python manage.py dbshell

# Check database service status
systemctl status postgresql  # or mysql/mariadb

# Verify connection settings
python manage.py shell
from django.db import connection
cursor = connection.cursor()
cursor.execute("SELECT 1")
print(cursor.fetchone())
```

**Common Fixes**:
1. Restart database service
2. Check firewall rules and network connectivity
3. Verify database credentials and permissions
4. Check connection pool settings

### Migration Issues

**Error**: "Migration failed" or "Table already exists"

**Solutions**:
```bash
# Check migration status
python manage.py showmigrations

# Fake apply problematic migration
python manage.py migrate --fake-initial

# Reset migrations (DANGEROUS - backup first!)
python manage.py migrate <app_name> zero
python manage.py makemigrations <app_name>
python manage.py migrate

# Manual migration repair
python manage.py shell
from django.db import connection
cursor = connection.cursor()
cursor.execute("SELECT * FROM django_migrations WHERE app='<app_name>'")
```

### Data Integrity Issues

**Symptoms**:
- Inconsistent data across related tables
- Foreign key constraint violations
- Missing or orphaned records

**Diagnosis Tools**:
```python
# Check for orphaned records
from django.db import models
from jobtracker.models import Job, Phase

# Find phases without valid jobs
orphaned_phases = Phase.objects.filter(job__isnull=True)
print(f"Found {orphaned_phases.count()} orphaned phases")

# Find jobs with invalid client references
invalid_jobs = Job.objects.filter(client__isnull=True)
print(f"Found {invalid_jobs.count()} jobs with invalid clients")
```

## Email and Notification Issues

### Email Not Sending

**Symptoms**:
- Users not receiving notifications
- System emails failing silently
- SMTP connection errors in logs

**Diagnostic Steps**:
```python
# Test email configuration
from django.core.mail import send_mail
from django.conf import settings

# Check email settings
print("Email Backend:", settings.EMAIL_BACKEND)
print("SMTP Host:", settings.EMAIL_HOST)
print("SMTP Port:", settings.EMAIL_PORT)
print("Use TLS:", settings.EMAIL_USE_TLS)

# Send test email
try:
    send_mail(
        'Test Email',
        'This is a test message.',
        settings.DEFAULT_FROM_EMAIL,
        ['test@example.com'],
        fail_silently=False,
    )
    print("Test email sent successfully")
except Exception as e:
    print(f"Email sending failed: {e}")
```

**Common Solutions**:
1. Verify SMTP server settings and credentials
2. Check firewall rules for SMTP port access
3. Validate SSL/TLS configuration
4. Test email server connectivity manually

### Notification Delivery Problems

**Missing Notifications**:
```python
# Check notification system status
from notifications.models import Notification

# Recent notifications
recent_notifications = Notification.objects.filter(
    created__gte=timezone.now() - timedelta(hours=24)
).order_by('-created')

for notification in recent_notifications[:10]:
    print(f"To: {notification.recipient}, Status: {notification.status}")

# Failed notifications
failed_notifications = Notification.objects.filter(
    status='failed',
    created__gte=timezone.now() - timedelta(days=7)
)
print(f"Failed notifications in last week: {failed_notifications.count()}")
```

## Job and Project Issues

### Jobs Not Progressing Through Workflow

**Symptoms**:
- Jobs stuck in particular status
- Status transitions not available
- Workflow buttons not responding

**Diagnostic Steps**:
```python
# Check job status and available transitions
from jobtracker.models import Job

job = Job.objects.get(id=2501)  # Replace with actual job ID
print(f"Current status: {job.get_status_display()}")

# Check available transitions
available_transitions = job.get_available_transitions()
print("Available transitions:", available_transitions)

# Check user permissions for transitions
user = User.objects.get(username='example_user')
for transition in available_transitions:
    can_transition = job.can_transition(transition, user)
    print(f"{transition}: {can_transition}")
```

**Common Solutions**:
1. Check user permissions for status transitions
2. Verify job has all required fields populated
3. Check for blocking validation rules
4. Review organizational unit permissions

### Missing or Incorrect Data in Jobs

**Data Inconsistency Issues**:
```python
# Verify job data integrity
from django.db import models
from jobtracker.models import Job, Phase

# Check jobs with missing required data
incomplete_jobs = Job.objects.filter(
    models.Q(title='') | 
    models.Q(client__isnull=True) |
    models.Q(unit__isnull=True)
)

print(f"Jobs with missing data: {incomplete_jobs.count()}")

# Check phases without time slots
phases_without_slots = Phase.objects.filter(timeslots__isnull=True)
print(f"Phases without time slots: {phases_without_slots.count()}")
```

## Scheduling and Calendar Issues

### Schedule Conflicts Not Detected

**Problem**: Double-booked resources or conflicting assignments

**Diagnosis**:
```python
# Check for scheduling conflicts
from jobtracker.models import TimeSlot
from django.db.models import Q
from datetime import datetime, timedelta

# Find overlapping time slots for same user
user_id = 1  # Replace with actual user ID
overlapping_slots = []

user_slots = TimeSlot.objects.filter(user_id=user_id).order_by('start_date')
for i, slot1 in enumerate(user_slots):
    for slot2 in user_slots[i+1:]:
        if (slot1.start_date < slot2.end_date and 
            slot1.end_date > slot2.start_date):
            overlapping_slots.append((slot1, slot2))

print(f"Found {len(overlapping_slots)} scheduling conflicts")
```

### Calendar Integration Problems

**iCal Feed Issues**:
```python
# Test calendar feed generation
from django.test import RequestFactory
from jobtracker.feeds import ScheduleFeed

factory = RequestFactory()
request = factory.get('/schedule/feed/test-key')

feed = ScheduleFeed()
try:
    response = feed(request, cal_key='test-key')
    print("Calendar feed generated successfully")
    print(f"Content length: {len(response.content)}")
except Exception as e:
    print(f"Calendar feed generation failed: {e}")
```

## File Upload and Storage Issues

### File Upload Failures

**Symptoms**:
- Files not uploading or saving
- Error messages about file size or type
- Storage quota exceeded errors

**Diagnostic Steps**:
```python
# Check storage configuration
from django.conf import settings
import os

print("Media Root:", settings.MEDIA_ROOT)
print("Media URL:", settings.MEDIA_URL)
print("File Upload Max Size:", settings.DATA_UPLOAD_MAX_MEMORY_SIZE)

# Check storage space
if os.path.exists(settings.MEDIA_ROOT):
    total, used, free = os.statvfs(settings.MEDIA_ROOT)
    print(f"Storage - Total: {total}, Used: {used}, Free: {free}")
else:
    print("Media root directory does not exist")

# Test file operations
test_file_path = os.path.join(settings.MEDIA_ROOT, 'test.txt')
try:
    with open(test_file_path, 'w') as f:
        f.write('test')
    os.remove(test_file_path)
    print("File operations working correctly")
except Exception as e:
    print(f"File operation failed: {e}")
```

## System Integration Issues

### API Authentication Failures

**Problem**: External systems cannot authenticate with CHAOTICA API

**Diagnosis**:
```python
# Verify API token functionality
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import User

# Check if user has valid token
user = User.objects.get(username='api_user')  # Replace with actual user
try:
    token = Token.objects.get(user=user)
    print(f"Token exists: {token.key}")
except Token.DoesNotExist:
    print("No token found for user")

# Test API endpoint access
import requests
response = requests.get(
    'http://localhost:8000/api/jobs/',
    headers={'Authorization': f'Token {token.key}'}
)
print(f"API Response: {response.status_code}")
```

### Third-Party Integration Failures

**Common Integration Problems**:
1. **Network Connectivity**
   ```bash
   # Test external service connectivity
   curl -I https://external-service.com/api
   nslookup external-service.com
   telnet external-service.com 443
   ```

2. **Certificate Issues**
   ```bash
   # Check SSL certificate validity
   openssl s_client -connect external-service.com:443 -servername external-service.com
   ```

3. **API Key/Token Issues**
   ```python
   # Test external API authentication
   import requests
   response = requests.get(
       'https://external-service.com/api/test',
       headers={'Authorization': 'Bearer your-token'},
       timeout=30
   )
   print(f"Status: {response.status_code}, Response: {response.text}")
   ```

## Preventive Measures

### System Health Monitoring

**Automated Health Checks**:
```python
# Create health check script
from django.core.management.base import BaseCommand
from django.db import connection
from django.core.cache import cache
import requests

class Command(BaseCommand):
    def handle(self, *args, **options):
        health_status = {
            'database': self.check_database(),
            'cache': self.check_cache(),
            'email': self.check_email(),
            'storage': self.check_storage()
        }
        
        for component, status in health_status.items():
            if status:
                self.stdout.write(f"✓ {component} is healthy")
            else:
                self.stdout.write(f"✗ {component} has issues")
    
    def check_database(self):
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            return True
        except:
            return False
    
    def check_cache(self):
        try:
            cache.set('health_check', 'ok', 60)
            return cache.get('health_check') == 'ok'
        except:
            return False
```

### Regular Maintenance Tasks

**Weekly Tasks**:
```bash
#!/bin/bash
# weekly_maintenance.sh

# Database maintenance
python manage.py clearsessions
python manage.py cleanup_notifications

# Log rotation and cleanup
find /var/log/chaotica -name "*.log" -mtime +30 -delete

# Cache cleanup
python manage.py shell -c "from django.core.cache import cache; cache.clear()"

# System updates check
apt list --upgradable

# Backup verification
python manage.py check_backup_integrity
```

### Monitoring and Alerting Setup

**Basic Monitoring Script**:
```python
import psutil
import requests
from datetime import datetime

def check_system_health():
    alerts = []
    
    # CPU usage
    cpu_percent = psutil.cpu_percent(interval=1)
    if cpu_percent > 80:
        alerts.append(f"High CPU usage: {cpu_percent}%")
    
    # Memory usage  
    memory = psutil.virtual_memory()
    if memory.percent > 85:
        alerts.append(f"High memory usage: {memory.percent}%")
    
    # Disk usage
    disk = psutil.disk_usage('/')
    disk_percent = (disk.used / disk.total) * 100
    if disk_percent > 90:
        alerts.append(f"Low disk space: {disk_percent}% used")
    
    # Web service availability
    try:
        response = requests.get('http://localhost:8000/health/', timeout=10)
        if response.status_code != 200:
            alerts.append(f"Web service unhealthy: HTTP {response.status_code}")
    except requests.exceptions.RequestException as e:
        alerts.append(f"Web service unreachable: {e}")
    
    return alerts

# Send alerts if any issues found
alerts = check_system_health()
if alerts:
    # Send email, Slack message, etc.
    print("System health alerts:", alerts)
```

## Getting Help

### Support Resources

**Documentation and Guides**:
- Check this troubleshooting guide first
- Review relevant user guide sections
- Consult API documentation for integration issues
- Search the knowledge base

**Log Files and Diagnostics**:
```bash
# Key log files to check
tail -f /var/log/chaotica/chaotica.log     # Application logs
tail -f /var/log/nginx/access.log           # Web server access
tail -f /var/log/postgresql/postgresql.log  # Database logs
journalctl -u chaotica -f                   # Systemd service logs
```

**Information to Collect for Support**:
- Exact error messages and screenshots
- Steps to reproduce the issue
- System information (OS, Python version, etc.)
- Recent changes or updates
- Relevant log file excerpts
- Output from diagnostic commands

### Emergency Procedures

**System Recovery Steps**:
1. **Database Issues**: Restore from backup
2. **Application Crashes**: Restart services and check logs
3. **Performance Issues**: Scale resources or restart services
4. **Security Incidents**: Follow incident response procedures
5. **Data Loss**: Activate disaster recovery procedures

**Emergency Contacts**:
- System Administrator: [Contact Information]
- Database Administrator: [Contact Information]  
- Security Team: [Contact Information]
- Management Escalation: [Contact Information]

## Related Topics

- [Performance Optimization](performance.md) - Detailed performance tuning guide
- [Security](../security/access_control.md) - Security policies and procedures
- [Administration](../administration/system_management.md) - System management procedures
- [Development](../development/getting_started.md) - Development environment troubleshooting