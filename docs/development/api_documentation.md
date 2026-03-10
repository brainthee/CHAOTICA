# API Documentation

CHAOTICA provides a comprehensive REST API built on Django REST Framework, enabling integration with external systems and custom application development. This guide covers available endpoints, authentication methods, and usage examples.

## API Overview

### Base Information

**Base URL**: `https://your-chaotica-instance.com/api/`
**API Version**: v1 (current)
**Protocol**: HTTPS (required)
**Format**: JSON (default), XML (optional)

### Architecture

**RESTful Design**:
- Standard HTTP methods (GET, POST, PUT, PATCH, DELETE)
- Resource-based URL structure
- Consistent response formats
- Standard HTTP status codes
- Pagination for large datasets

**Django REST Framework**:
- Browsable API interface for development
- Built-in serialization and validation
- Permission and authentication integration
- Filtering and search capabilities
- Automatic API documentation generation

## Authentication

### Authentication Methods

**Session Authentication**:
```http
GET /api/jobs/
Cookie: sessionid=your_session_id_here
```

**Token Authentication**:
```http
GET /api/jobs/
Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b
```

**Basic Authentication** (Development Only):
```http
GET /api/jobs/
Authorization: Basic dXNlcm5hbWU6cGFzc3dvcmQ=
```

### API Token Management

**Creating API Tokens**:
1. Log into CHAOTICA web interface
2. Navigate to Profile → API Tokens
3. Click "Generate New Token"
4. Copy and securely store the token
5. Use in Authorization header

**Token Security**:
- Tokens are equivalent to passwords
- Store securely and never commit to version control
- Rotate tokens regularly
- Revoke unused or compromised tokens
- Use environment variables for token storage

## Core Endpoints

### Users API

**List Users**:
```http
GET /api/users/
```

Response:
```json
{
    "count": 25,
    "next": "http://api/users/?page=2",
    "previous": null,
    "results": [
        {
            "id": 1,
            "username": "john.doe",
            "email": "john.doe@company.com",
            "first_name": "John",
            "last_name": "Doe",
            "is_active": true,
            "date_joined": "2023-01-15T10:30:00Z",
            "profile": {
                "job_title": "Senior Security Consultant",
                "phone": "+1-555-0123",
                "skills": ["Web Application Testing", "Infrastructure Assessment"]
            }
        }
    ]
}
```

**Get User Details**:
```http
GET /api/users/{user_id}/
```

**Update User**:
```http
PATCH /api/users/{user_id}/
Content-Type: application/json

{
    "first_name": "Jonathan",
    "profile": {
        "phone": "+1-555-0199"
    }
}
```

### Jobs API

**List Jobs**:
```http
GET /api/jobs/
```

Query Parameters:
- `status`: Filter by job status
- `client`: Filter by client ID
- `unit`: Filter by organizational unit
- `search`: Full-text search
- `ordering`: Sort results (`-created`, `title`, etc.)

Response:
```json
{
    "count": 150,
    "next": "http://api/jobs/?page=2",
    "previous": null,
    "results": [
        {
            "id": 2501,
            "title": "E-commerce Security Assessment",
            "client": {
                "id": 15,
                "name": "Acme Corporation",
                "slug": "acme-corp"
            },
            "status": "in_progress",
            "status_display": "In Progress",
            "created": "2023-03-15T14:20:00Z",
            "start_date": "2023-04-01",
            "end_date": "2023-04-15",
            "unit": {
                "id": 3,
                "name": "Security Consulting",
                "slug": "security-consulting"
            },
            "account_manager": {
                "id": 5,
                "username": "sarah.johnson",
                "display_name": "Sarah Johnson"
            },
            "phases": [
                {
                    "id": 450,
                    "name": "Web Application Assessment",
                    "service": "Web Application Testing",
                    "status": "testing"
                }
            ]
        }
    ]
}
```

**Create Job**:
```http
POST /api/jobs/
Content-Type: application/json

{
    "title": "Network Security Review",
    "client": 15,
    "unit": 3,
    "description": "Comprehensive network security assessment",
    "start_date": "2023-05-01",
    "end_date": "2023-05-20",
    "account_manager": 5
}
```

**Job Status Transitions**:
```http
POST /api/jobs/{job_id}/transition/
Content-Type: application/json

{
    "transition": "to_in_progress",
    "comment": "All prerequisites completed, starting assessment work"
}
```

### Clients API

**List Clients**:
```http
GET /api/client/
```

**Client Details**:
```http
GET /api/client/{client_id}/
```

Response:
```json
{
    "id": 15,
    "name": "Acme Corporation",
    "slug": "acme-corp",
    "short_name": "ACME",
    "industry": "E-commerce",
    "website": "https://acme-corp.com",
    "address": {
        "street": "123 Business Ave",
        "city": "New York",
        "state": "NY",
        "postal_code": "10001",
        "country": "US"
    },
    "contacts": [
        {
            "id": 89,
            "name": "Jane Smith",
            "email": "jane.smith@acme-corp.com",
            "phone": "+1-555-0199",
            "role": "CISO",
            "type": "security"
        }
    ],
    "framework_agreements": [
        {
            "id": 12,
            "name": "2023 Security Services Framework",
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
            "total_value": 500000.00,
            "remaining_value": 285000.00
        }
    ],
    "active_jobs_count": 3,
    "total_jobs_count": 18
}
```

### Organizational Units API

**List Units**:
```http
GET /api/orgunit/
```

**Unit Details with Team**:
```http
GET /api/orgunit/{unit_id}/
```

Response:
```json
{
    "id": 3,
    "name": "Security Consulting",
    "slug": "security-consulting",
    "description": "Comprehensive security assessment services",
    "members": [
        {
            "user": {
                "id": 1,
                "username": "john.doe",
                "display_name": "John Doe"
            },
            "roles": ["consultant", "tqa"],
            "skills": ["Web Application Testing", "Infrastructure Assessment"]
        }
    ],
    "active_jobs": 12,
    "capacity_utilization": 0.85
}
```

### Notes API

**List Notes**:
```http
GET /api/notes/?content_type=job&object_id=2501
```

**Create Note**:
```http
POST /api/notes/
Content-Type: application/json

{
    "content_type": "job",
    "object_id": 2501,
    "note": "Client has requested additional web service testing",
    "category": "scope_change"
}
```

## Advanced API Features

### Filtering and Search

**Filter Examples**:
```http
# Jobs by status and client
GET /api/jobs/?status=in_progress&client=15

# Jobs created in last 30 days
GET /api/jobs/?created__gte=2023-03-01

# Users by organizational unit
GET /api/users/?profile__units__in=3

# Full-text search across jobs
GET /api/jobs/?search=penetration testing
```

**Advanced Filters**:
- Date ranges: `__gte`, `__lte`, `__range`
- Text matching: `__icontains`, `__iexact`, `__startswith`
- List membership: `__in`, `__contains`
- Null checks: `__isnull`
- Relational: `__related_field__lookup`

### Pagination

**Page-based Pagination**:
```http
GET /api/jobs/?page=2&page_size=50
```

Response:
```json
{
    "count": 150,
    "next": "http://api/jobs/?page=3&page_size=50",
    "previous": "http://api/jobs/?page=1&page_size=50",
    "results": [...]
}
```

**Cursor-based Pagination** (for large datasets):
```http
GET /api/jobs/?cursor=cD0yMDIzLTAzLTE1KzEwJTNBMDA%3D
```

### Ordering

**Sorting Examples**:
```http
# Sort by creation date (newest first)
GET /api/jobs/?ordering=-created

# Sort by title alphabetically
GET /api/jobs/?ordering=title

# Multiple sort fields
GET /api/jobs/?ordering=status,-created
```

### Field Selection

**Include/Exclude Fields**:
```http
# Only specific fields
GET /api/jobs/?fields=id,title,status,client

# Exclude heavy fields
GET /api/jobs/?exclude=description,notes
```

## Bulk Operations

### Bulk Updates

**Bulk Status Changes**:
```http
PATCH /api/jobs/bulk_update/
Content-Type: application/json

{
    "ids": [2501, 2502, 2503],
    "data": {
        "status": "completed"
    }
}
```

### Batch Processing

**Batch Job Creation**:
```http
POST /api/jobs/batch/
Content-Type: application/json

{
    "jobs": [
        {
            "title": "Q1 Security Review - Division A",
            "client": 15,
            "unit": 3
        },
        {
            "title": "Q1 Security Review - Division B", 
            "client": 15,
            "unit": 3
        }
    ]
}
```

## Data Export

### Export Formats

**CSV Export**:
```http
GET /api/jobs/export/?format=csv
Accept: text/csv
```

**Excel Export**:
```http
GET /api/jobs/export/?format=xlsx
Accept: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
```

**JSON Export**:
```http
GET /api/jobs/export/?format=json&fields=id,title,status,client__name
```

### Scheduled Exports

**Create Export Job**:
```http
POST /api/exports/
Content-Type: application/json

{
    "resource": "jobs",
    "format": "xlsx",
    "filters": {"status": "completed"},
    "schedule": "daily",
    "email_recipients": ["manager@company.com"]
}
```

## Webhooks

### Webhook Configuration

**Register Webhook**:
```http
POST /api/webhooks/
Content-Type: application/json

{
    "url": "https://your-system.com/chaotica-webhook",
    "events": ["job.status_changed", "phase.completed"],
    "secret": "your-webhook-secret",
    "active": true
}
```

### Webhook Events

**Job Events**:
- `job.created`
- `job.status_changed`
- `job.updated`
- `job.deleted`

**Phase Events**:
- `phase.created`
- `phase.status_changed`
- `phase.completed`

**User Events**:
- `user.created`
- `user.updated`
- `user.login`

**Webhook Payload Example**:
```json
{
    "event": "job.status_changed",
    "timestamp": "2023-03-20T15:30:00Z",
    "data": {
        "job_id": 2501,
        "old_status": "scoping",
        "new_status": "in_progress",
        "changed_by": {
            "id": 5,
            "username": "sarah.johnson"
        }
    }
}
```

## Error Handling

### HTTP Status Codes

**Success Codes**:
- `200 OK`: Successful GET, PUT, PATCH requests
- `201 Created`: Successful POST requests
- `204 No Content`: Successful DELETE requests

**Client Error Codes**:
- `400 Bad Request`: Invalid request data
- `401 Unauthorized`: Authentication required
- `403 Forbidden`: Permission denied
- `404 Not Found`: Resource not found
- `409 Conflict`: Resource conflict (duplicate, constraint violation)
- `422 Unprocessable Entity`: Validation errors

**Server Error Codes**:
- `500 Internal Server Error`: Server-side error
- `502 Bad Gateway`: Upstream service error
- `503 Service Unavailable`: Temporary service interruption

### Error Response Format

```json
{
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "The submitted data contains validation errors",
        "details": {
            "title": ["This field is required"],
            "start_date": ["Date must be in the future"]
        },
        "timestamp": "2023-03-20T15:30:00Z",
        "request_id": "req_abc123def456"
    }
}
```

## Rate Limiting

### Limits

**Default Limits**:
- Authenticated users: 1000 requests/hour
- Anonymous users: 100 requests/hour
- Burst limit: 20 requests/minute

**Rate Limit Headers**:
```http
HTTP/1.1 200 OK
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1679327400
```

### Rate Limit Exceeded

```http
HTTP/1.1 429 Too Many Requests
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1679327400

{
    "error": {
        "code": "RATE_LIMIT_EXCEEDED",
        "message": "Rate limit exceeded. Try again in 60 seconds.",
        "retry_after": 60
    }
}
```

## SDK and Libraries

### Python Client

```python
import chaotica_client

# Initialize client
client = chaotica_client.Client(
    base_url="https://your-instance.com",
    token="your-api-token"
)

# List jobs
jobs = client.jobs.list(status="in_progress")

# Create new job
job = client.jobs.create({
    "title": "Security Assessment",
    "client": 15,
    "unit": 3
})

# Update job status
client.jobs.transition(job.id, "to_completed")
```

### JavaScript/Node.js Client

```javascript
const ChaoticaClient = require('chaotica-js-client');

const client = new ChaoticaClient({
    baseUrl: 'https://your-instance.com',
    token: 'your-api-token'
});

// Async/await usage
const jobs = await client.jobs.list({ status: 'in_progress' });

// Promise usage
client.jobs.get(2501)
    .then(job => console.log(job.title))
    .catch(error => console.error(error));
```

## Integration Examples

### Workflow Automation

**Slack Integration**:
```python
import requests
import json

# CHAOTICA webhook handler
def handle_job_completed(webhook_data):
    job_id = webhook_data['data']['job_id']
    
    # Get job details
    job = client.jobs.get(job_id)
    
    # Send Slack notification
    slack_message = {
        "text": f"Job completed: {job['title']}",
        "attachments": [{
            "color": "good",
            "fields": [
                {"title": "Client", "value": job['client']['name']},
                {"title": "Duration", "value": f"{job['duration_days']} days"}
            ]
        }]
    }
    
    requests.post(slack_webhook_url, json=slack_message)
```

### Business Intelligence

**PowerBI Integration**:
```python
# Export data for PowerBI
def export_project_metrics():
    jobs = client.jobs.list(
        status__in=['completed', 'delivered'],
        created__gte='2023-01-01'
    )
    
    metrics = []
    for job in jobs:
        metrics.append({
            'job_id': job['id'],
            'client_name': job['client']['name'],
            'duration_days': job['duration_days'],
            'team_size': len(job['team_members']),
            'revenue': job['total_revenue'],
            'completion_date': job['completion_date']
        })
    
    # Save to data warehouse or export to file
    return metrics
```

## Testing and Development

### API Testing

**Using curl**:
```bash
# Test authentication
curl -H "Authorization: Token your-token" \
     https://your-instance.com/api/users/

# Create test job
curl -X POST \
     -H "Authorization: Token your-token" \
     -H "Content-Type: application/json" \
     -d '{"title":"Test Job","client":1,"unit":1}' \
     https://your-instance.com/api/jobs/
```

**Using HTTPie**:
```bash
# List jobs with filters
http GET your-instance.com/api/jobs/ \
     "Authorization:Token your-token" \
     status==in_progress \
     client==15

# Update job
http PATCH your-instance.com/api/jobs/2501/ \
     "Authorization:Token your-token" \
     title="Updated Job Title"
```

### Development Environment

**Local API Server**:
```bash
# Start development server
cd app/
python manage.py runserver 8000

# API will be available at:
# http://localhost:8000/api/
```

**API Documentation**:
- Browsable API: `http://localhost:8000/api/`
- OpenAPI Schema: `http://localhost:8000/api/schema/`
- ReDoc Documentation: `http://localhost:8000/api/docs/`

## Security Considerations

### API Security

**Authentication Security**:
- Always use HTTPS in production
- Rotate API tokens regularly
- Use environment variables for sensitive data
- Implement proper access controls
- Monitor for suspicious API usage

**Data Protection**:
- Validate all input data
- Sanitize output data
- Implement proper rate limiting
- Use CORS headers appropriately
- Log security-relevant events

**Best Practices**:
- Principle of least privilege for API access
- Regular security assessments
- Keep dependencies updated
- Implement proper error handling
- Use secure communication channels

## Related Topics

- [User Management](../user_guide/team/user_management.md) - User authentication and permissions
- [Integration Guides](../integration/apis.md) - External system integration examples
- [Security](../security/access_control.md) - Security policies and procedures
- [Development](getting_started.md) - Development environment setup