"""Shared logic to seed EmailTemplate rows from the filesystem templates.

Imported by both the ``seed_email_templates`` management command and the data
migration, so the extraction logic lives in one place. Extraction is
deterministic because every email template uses the same ``{% block content %}``
structure inherited from ``email_base.html``.
"""
import re

from django.template.loader import get_template

# slug (== filesystem path) -> metadata. Slugs equal the paths the senders pass.
TEMPLATE_DEFS = [
    # slug, name, description, action_label
    ('emails/user_invite.html', 'User Invite', 'Sent when a user is invited to CHAOTICA.', 'Accept invitation'),
    ('emails/test_email.html', 'Test Email', 'Sent from the admin test-email action.', 'View'),
    ('emails/leave_requested.html', 'Leave Requested', 'Sent to approvers when leave is requested.', 'Review request'),
    ('emails/leave_approved.html', 'Leave Approved', 'Sent to the requester when leave is approved.', 'View'),
    ('emails/leave_declined.html', 'Leave Declined', 'Sent to the requester when leave is declined.', 'View'),
    ('emails/leave_cancelled.html', 'Leave Cancelled', 'Sent when a leave request is cancelled.', 'View'),
    ('emails/onboarding_reminder.html', 'Onboarding Reminder', 'Periodic client onboarding reminder.', 'View'),
    ('emails/job_content.html', 'Job Notification', 'Job status change notifications.', 'View job'),
    ('emails/phase_content.html', 'Phase Notification', 'Phase status change notifications.', 'View phase'),
    # Currently unreferenced templates - seeded for completeness/future use.
    ('emails/leave.html', 'Leave (legacy)', 'Legacy leave email (currently unused).', 'View'),
    ('emails/orgunit/accepted.html', 'Org Unit Membership Accepted', 'Org unit membership accepted (currently unused).', 'View'),
    ('emails/orgunit/rejected.html', 'Org Unit Membership Rejected', 'Org unit membership rejected (currently unused).', 'View'),
    ('registration/account_activation_email.html', 'Account Activation', 'Account activation email (currently unused).', 'Activate'),
]

_CONTENT_BLOCK_RE = re.compile(
    r'{%\s*block\s+content\s*%}(.*?){%\s*endblock(?:\s+content)?\s*%}', re.DOTALL
)


def _read_template_source(slug):
    """Return the raw source of the filesystem template, or None if missing."""
    try:
        template = get_template(slug)
    except Exception:
        return None
    origin = getattr(template, 'origin', None)
    path = getattr(origin, 'name', None)
    if not path:
        return None
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            return fh.read()
    except OSError:
        return None


def extract_content(source):
    """Extract the {% block content %} inner source.

    Returns ``(body_html, extends_base)``. Falls back to the whole file with
    ``extends_base=False`` if no content block is present.
    """
    match = _CONTENT_BLOCK_RE.search(source)
    if match:
        return match.group(1).strip(), True
    return source, False


def seed_email_templates(force=False, stdout=None):
    """Create/update EmailTemplate rows from the filesystem templates.

    Idempotent: existing rows are only overwritten when ``force`` is True or the
    row has not been customised by an admin (``is_customized`` False).
    Returns a summary dict.
    """
    from .models import EmailTemplate

    def log(msg):
        if stdout is not None:
            stdout.write(msg)

    created = updated = skipped = missing = 0

    for slug, name, description, action_label in TEMPLATE_DEFS:
        source = _read_template_source(slug)
        if source is None:
            missing += 1
            log(f"  MISSING template file for '{slug}' - skipped")
            continue

        body_html, extends_base = extract_content(source)
        existing = EmailTemplate.objects.filter(slug=slug).first()

        if existing is None:
            EmailTemplate.objects.create(
                slug=slug, name=name, description=description,
                subject='{{ title }}', body_html=body_html, extends_base=extends_base,
                action_label=action_label, is_seeded=True, is_customized=False,
            )
            created += 1
            log(f"  Created '{slug}'")
            continue

        if existing.is_customized and not force:
            skipped += 1
            log(f"  Skipped customised '{slug}' (use --force to overwrite)")
            continue

        existing.name = name
        existing.description = description
        existing.body_html = body_html
        existing.extends_base = extends_base
        existing.action_label = action_label
        existing.is_seeded = True
        if force:
            existing.is_customized = False
        existing.save()
        updated += 1
        log(f"  Updated '{slug}'")

    summary = {'created': created, 'updated': updated, 'skipped': skipped, 'missing': missing}
    log(f"Email templates: {summary}")
    return summary
