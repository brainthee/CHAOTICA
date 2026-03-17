# Testing Guide

## Quick Start

### Running Tests

```bash
# Run all tests
cd app && python manage.py test --verbosity=2 --keepdb

# Run a specific app's tests
cd app && python manage.py test jobtracker.tests --verbosity=2 --keepdb

# Run a specific test file
cd app && python manage.py test jobtracker.tests.test_qualification_models --verbosity=2 --keepdb

# Run a specific test class
cd app && python manage.py test jobtracker.tests.test_qualification_models.QualificationTests --verbosity=2 --keepdb

# Run a single test method
cd app && python manage.py test jobtracker.tests.test_qualification_models.QualificationTests.test_qualification_creation --verbosity=2 --keepdb
```

The `--keepdb` flag reuses the test database between runs, significantly speeding up test execution.

## Project Conventions

### Framework

CHAOTICA uses Django's built-in `TestCase` framework. Do not use pytest.

### File Layout

Tests live in a `tests/` package within each Django app:

```
app/<appname>/tests/
├── __init__.py              # Required — makes it a Python package
├── test_models.py           # Model tests
├── test_forms.py            # Form tests
├── test_views_<area>.py     # View tests (split by area)
└── test_tasks.py            # Celery task tests
```

### Naming Conventions

- **Files:** `test_<system>_<layer>.py` (e.g. `test_qualification_models.py`, `test_skill_models.py`)
- **Classes:** One test class per model, form, or view group (e.g. `QualificationTests`, `AwardingBodyTests`)
- **Methods:** `test_<what_is_being_tested>` — be descriptive (e.g. `test_validity_period_display_years_months_days`)

## Critical: Custom SessionMiddleware

!!! warning "Most Common Gotcha"
    CHAOTICA has a custom `SessionMiddleware` (`chaotica_utils/middleware/session.py`) that validates the `HTTP_HOST` header on every request. Django's test client does **not** set this header by default, causing **all view test requests to return HTTP 400**.

### The Fix

Always pass `HTTP_HOST="testserver"` when creating the test client:

```python
from django.test import TestCase, Client as TestClient

class MyViewTestCase(TestCase):
    """Base class for all view tests."""
    def setUp(self):
        super().setUp()
        self.client = TestClient(HTTP_HOST="testserver")
```

!!! note
    Model-only tests do not make HTTP requests and do not need this.

## Authentication Patterns

### Login URL

The login URL is `/auth/login/` (not `/login/`). When testing redirects for unauthenticated users:

```python
def test_requires_login(self):
    resp = self.client.get(reverse("my_view"))
    self.assertEqual(resp.status_code, 302)
    self.assertIn("/auth/login/", resp.url)
```

### Creating Test Users

```python
from chaotica_utils.models import User

# In setUp():
self.user = User.objects.create_user(
    email="user@test.com",
    password="testpass123"
)
```

### Logging In

```python
self.client.login(email="user@test.com", password="testpass123")
```

## Permission-Gated Views (django-guardian)

Views that use `PermissionRequiredMixin` with `return_403=True` return **HTTP 403** for anonymous users, not a 302 redirect.

### Assigning Permissions

```python
from guardian.shortcuts import assign_perm

# Global permission
assign_perm("jobtracker.view_qualification", self.user)

# Object-level permission
assign_perm("can_approve_leave_requests", self.user, org_unit)
```

### Testing Permission Denied

```python
def test_requires_permission(self):
    resp = self.client.get(reverse("protected_view"))
    # Could be 302 (LoginRequired) or 403 (PermissionRequired)
    self.assertIn(resp.status_code, [302, 403])
```

## Testing Models

### Standard Model Test Pattern

```python
class MyModelTests(TestCase):
    def setUp(self):
        # Create dependencies
        self.user = User.objects.create_user(
            email="user@test.com", password="testpass123"
        )

    def test_creation(self):
        obj = MyModel.objects.create(name="Test", user=self.user)
        self.assertEqual(obj.name, "Test")

    def test_str(self):
        obj = MyModel.objects.create(name="Test", user=self.user)
        self.assertEqual(str(obj), "Test")

    def test_auto_slug(self):
        obj = MyModel.objects.create(name="Test", user=self.user)
        self.assertTrue(obj.slug)

    def test_get_absolute_url(self):
        obj = MyModel.objects.create(name="Test", user=self.user)
        url = obj.get_absolute_url()
        self.assertIn(obj.slug, url)
```

### Testing Validation

```python
from django.core.exceptions import ValidationError

def test_clean_raises_on_invalid(self):
    obj = MyModel(invalid_field=-1)
    with self.assertRaises(ValidationError):
        obj.clean()
```

### Testing State Transitions

```python
def test_authorise_sets_fields(self):
    request = LeaveRequest.objects.create(...)
    request.authorise(self.manager)
    self.assertTrue(request.authorised)
    self.assertEqual(request.authorised_by, self.manager)
```

## Testing Forms

### Basic Form Tests

```python
def test_form_valid(self):
    form = MyForm(data={"name": "Test", "value": 42})
    self.assertTrue(form.is_valid(), form.errors)

def test_form_fields(self):
    form = MyForm()
    self.assertIn("name", form.fields)
```

### Crispy Forms Layout Inspection

!!! warning
    `form.as_p()` renders **all** model fields regardless of the crispy layout. To check which fields are actually shown in the form, walk the layout tree:

```python
def _get_layout_field_names(self, form):
    """Extract field names from the crispy forms layout."""
    fields = []
    def _walk(layout_obj):
        if hasattr(layout_obj, 'fields'):
            for f in layout_obj.fields:
                if isinstance(f, str):
                    fields.append(f)
                else:
                    _walk(f)
    _walk(form.helper.layout)
    return fields

def test_form_hides_field(self):
    form = MyForm(instance=record)
    layout_fields = self._get_layout_field_names(form)
    self.assertNotIn("hidden_field", layout_fields)
```

## Testing Views

### AJAX / JSON Views

Many CHAOTICA views return JSON for modal forms:

```python
def test_add_returns_json(self):
    resp = self.client.get(reverse("add_thing"))
    self.assertEqual(resp.status_code, 200)
    data = resp.json()
    self.assertIn("html_form", data)

def test_add_post_valid(self):
    resp = self.client.post(
        reverse("add_thing"),
        {"name": "Test", "value": 42},
    )
    data = resp.json()
    self.assertTrue(data["form_is_valid"])
```

### POST-Only Views

```python
def test_get_not_allowed(self):
    resp = self.client.get(reverse("action_endpoint", args=[record.pk]))
    self.assertEqual(resp.status_code, 405)
```

### Testing Record Isolation

Ensure users can only access their own records:

```python
def test_other_users_record_404(self):
    other_record = Record.objects.create(user=self.other_user, ...)
    resp = self.client.get(
        reverse("update_record", args=[other_record.pk])
    )
    self.assertEqual(resp.status_code, 404)
```

### Manager / Acting Manager Patterns

```python
def setUp(self):
    super().setUp()
    self.manager = User.objects.create_user(
        email="manager@test.com", password="testpass123"
    )
    self.user = User.objects.create_user(
        email="user@test.com", password="testpass123"
    )
    self.user.manager = self.manager
    self.user.save()

def test_acting_manager_access(self):
    self.user.manager = None
    self.user.acting_manager = self.manager
    self.user.save()
    # ... test that acting_manager has same access as manager
```

## Common Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| Missing `HTTP_HOST` | All view requests return 400 | Use `Client(HTTP_HOST="testserver")` |
| Wrong login URL | Redirect assertions fail | Check for `/auth/login/`, not `/login/` |
| PermissionRequiredMixin | Expected 302, got 403 | Use `assertIn(status, [302, 403])` |
| Crispy layout vs `as_p()` | Field appears present when hidden | Walk `form.helper.layout` tree |
| Missing `super().setUp()` | Parent fixtures not created | Always call `super().setUp()` in subclass |
| `auto_now_add` fields | Can't set timestamp in test | Use `Model.objects.filter().update()` after create |

## Existing Test Coverage

| App | File | Tests | Coverage |
|-----|------|-------|----------|
| jobtracker | `test_qualification_models.py` | 30 | QualificationTag, AwardingBody, Qualification, QualificationRecord |
| jobtracker | `test_qualification_forms.py` | 14 | OwnQualificationRecordForm, QualificationForm, AwardingBodyForm |
| jobtracker | `test_qualification_views_own.py` | 27 | Own qualification CRUD, transitions, date validation |
| jobtracker | `test_qualification_views_team.py` | 17 | Team list, verify/unverify, manager access |
| jobtracker | `test_qualification_views_catalogue.py` | 8 | Permission-gated list/detail views |
| jobtracker | `test_qualification_tasks.py` | 5 | Expiry check cron task |
| jobtracker | `test_skill_models.py` | 25 | SkillCategory, Skill, UserSkill, learning paths |
| jobtracker | `test_client_models.py` | 25 | Client, Contact, ClientOnboarding, FrameworkAgreement |
| chaotica_utils | `test_utils.py` | 30 | Utility functions (slug, percentage, dates, etc.) |
| chaotica_utils | `test_job_levels.py` | 15 | JobLevel, UserJobLevel |
| chaotica_utils | `test_leave.py` | 20 | LeaveRequest state machine |
| notifications | `test_models.py` | 20 | Notification, Subscription, OptOut, Category |

Use the qualification tests as a comprehensive reference example — they demonstrate all the patterns described above.
