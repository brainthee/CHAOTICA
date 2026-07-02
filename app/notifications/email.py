"""Central helpers for rendering and sending templated emails.

``render_email`` resolves an email template by slug - preferring an active DB
``EmailTemplate`` and falling back to the filesystem template of the same path,
so existing emails keep working unchanged. ``send_templated_email`` is the
single send path, applying the same gating the app has always used
(``config.EMAIL_ENABLED``, ``DEFAULT_FROM_EMAIL``, and the "skip addresses
without an @" guard).
"""
import logging

import django.core.mail
from django.template.loader import render_to_string
from constance import config

logger = logging.getLogger(__name__)


def render_email(slug, context):
    """Render an email by slug. Returns ``(subject, html, text)``.

    Uses the active DB template if present, else the filesystem template at
    ``slug`` (identical to the historical behaviour).
    """
    from .models import EmailTemplate

    template = EmailTemplate.objects.filter(slug=slug, is_active=True).first()
    if template is not None:
        return template.render(context)

    # Filesystem fallback - unchanged legacy behaviour.
    html = render_to_string(slug, context)
    subject = str(context.get('title', ''))
    text = str(context.get('message', ''))
    return subject, html, text


def send_templated_email(slug, context, recipients, fail_silently=False):
    """Render ``slug`` with ``context`` and email it to ``recipients``.

    Returns True if a send was attempted, False if skipped (email disabled or no
    valid recipient). Mirrors the app's existing gating so callers can swap in
    without behaviour changes.
    """
    if not config.EMAIL_ENABLED:
        return False

    valid = [r for r in recipients if r and '@' in r]
    if not valid:
        return False

    subject, html, text = render_email(slug, context)
    django.core.mail.send_mail(
        subject=subject,
        message=text,
        from_email=None,  # falls back to DEFAULT_FROM_EMAIL
        recipient_list=valid,
        html_message=html,
        fail_silently=fail_silently,
    )
    return True
