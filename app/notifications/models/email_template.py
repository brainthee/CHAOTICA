import re

from django.db import models
from django.core.exceptions import ValidationError
from django.template import Template, Context, TemplateSyntaxError

# Template tags that are disallowed in admin-edited email bodies. These either
# load arbitrary tag libraries or pull in other templates/files, widening the
# template-injection surface beyond simple value interpolation.
_FORBIDDEN_TAG_RE = re.compile(r'{%\s*(load|include|ssi|debug|extends|block|endblock)\b')


class EmailTemplate(models.Model):
    """An admin-editable email template stored in the database.

    Emails are rendered from the active DB row for a given ``slug`` if one
    exists, otherwise the sender falls back to the filesystem template of the
    same path (see ``notifications.email.render_email``). This keeps every
    existing email working while letting non-developers edit wording in-app.

    The ``slug`` deliberately equals the filesystem template path (e.g.
    ``emails/leave_requested.html``) so it maps 1:1 onto the path strings that
    ``Notification.email_template`` and the direct senders already pass.

    Editors edit only the *content* (and subject / button label); the shared
    responsive shell stays in ``email_base.html`` under version control and is
    re-applied at render time when ``extends_base`` is set.
    """

    slug = models.CharField(
        max_length=255, unique=True,
        help_text="Template key - equals the filesystem template path it overrides, "
                  "e.g. 'emails/leave_requested.html'.",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, help_text="What triggers this email.")

    subject = models.CharField(
        max_length=255, default='{{ title }}',
        help_text="Email subject. Supports placeholders, e.g. {{ title }}.",
    )
    body_html = models.TextField(
        help_text="The editable HTML content of the email. When 'Extends base' is on, this is "
                  "injected into the shared email shell - do not include <html>/<body> tags.",
    )
    body_text = models.TextField(
        blank=True,
        help_text="Optional plain-text version. If blank, the notification message is used.",
    )
    extends_base = models.BooleanField(
        default=True,
        help_text="Wrap the content in the shared email_base.html shell (recommended).",
    )
    action_label = models.CharField(
        max_length=100, default='View',
        help_text="Text for the call-to-action button (shown when the email has an action link).",
    )
    available_context = models.TextField(
        blank=True,
        help_text="Documentation for editors: the placeholders available to this template.",
    )

    is_active = models.BooleanField(
        default=True,
        help_text="If off, the filesystem template is used instead (kill-switch).",
    )
    is_seeded = models.BooleanField(default=False, editable=False)
    is_customized = models.BooleanField(
        default=False,
        help_text="Set automatically when an admin edits this template; protects it from re-seeding.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Email Template'
        verbose_name_plural = 'Email Templates'

    def __str__(self):
        return self.name or self.slug

    def clean(self):
        # Reject dangerous tags in the content body — unconditionally, so a
        # standalone (extends_base=False) template can't smuggle in {% load %} /
        # {% include %} / {% ssi %} etc. either.
        if _FORBIDDEN_TAG_RE.search(self.body_html or ''):
            raise ValidationError({
                'body_html': "Content may not use {% load %}, {% include %}, {% extends %}, "
                             "{% block %}, {% ssi %} or {% debug %} tags.",
            })
        # Ensure subject and body compile.
        for field_name, source in (('subject', self.subject), ('body_html', self.build_source())):
            try:
                Template(source or '')
            except TemplateSyntaxError as e:
                raise ValidationError({field_name: f"Template error: {e}"})

    def build_source(self):
        """Return the full template source string to render."""
        if not self.extends_base:
            return self.body_html or ''
        # Re-apply the shared shell, filling only the editable blocks.
        return (
            "{% extends 'email_base.html' %}"
            "{% block title %}{{ title }}{% endblock %}"
            "{% block content %}" + (self.body_html or '') + "{% endblock %}"
            "{% block action_block %}"
            "{% if action_link %}"
            "<a href=\"{{ action_link }}\" style=\"color:#ffffff;text-decoration:none;display:block;"
            "padding:12px 24px;font-weight:700;\">{{ action_label }}</a>"
            "{% endif %}"
            "{% endblock %}"
        )

    def render(self, context):
        """Render this template against ``context``.

        Returns a ``(subject, html, text)`` tuple.
        """
        render_ctx = dict(context)
        render_ctx.setdefault('action_label', self.action_label)

        subject = Template(self.subject or '{{ title }}').render(Context(render_ctx)).strip()
        if not subject:
            subject = str(render_ctx.get('title', ''))

        html = Template(self.build_source()).render(Context(render_ctx))

        if self.body_text:
            text = Template(self.body_text).render(Context(render_ctx))
        else:
            text = str(render_ctx.get('message', ''))

        return subject, html, text
