from django.test import TestCase, SimpleTestCase
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string

from notifications.models import EmailTemplate
from notifications.email import render_email
from notifications.seed_email_templates import extract_content


CTX = {
    'title': 'Hello there',
    'message': 'A message body',
    'action_link': 'https://example.com/go',
    'user': 'Alice',
    'SITE_DOMAIN': 'd', 'SITE_PROTO': 'https',
}


class ExtractContentTests(SimpleTestCase):
    def test_extracts_inner_content_block(self):
        source = "{% extends 'email_base.html' %}{% block content %}Hi {{ user }}{% endblock %}"
        body, extends = extract_content(source)
        self.assertEqual(body, 'Hi {{ user }}')
        self.assertTrue(extends)

    def test_falls_back_to_whole_file_without_block(self):
        source = "<p>Standalone content</p>"
        body, extends = extract_content(source)
        self.assertEqual(body, source)
        self.assertFalse(extends)


class EmailTemplateRenderTests(SimpleTestCase):
    def test_render_injects_content_and_button(self):
        tpl = EmailTemplate(
            slug='emails/x.html', name='X', subject='{{ title }}',
            body_html='Dear {{ user }}, {{ message }}', extends_base=True, action_label='Go now',
        )
        subject, html, text = tpl.render(CTX)
        self.assertEqual(subject, 'Hello there')
        self.assertIn('Dear Alice, A message body', html)
        self.assertIn('https://example.com/go', html)   # button link
        self.assertIn('Go now', html)                    # button label
        self.assertEqual(text, 'A message body')         # falls back to message

    def test_subject_falls_back_to_title_when_blank(self):
        tpl = EmailTemplate(slug='emails/y.html', name='Y', subject='', body_html='x', extends_base=False)
        subject, _, _ = tpl.render(CTX)
        self.assertEqual(subject, 'Hello there')

    def test_clean_rejects_forbidden_tags(self):
        tpl = EmailTemplate(slug='emails/z.html', name='Z', subject='{{ title }}',
                            body_html='{% load static %}x', extends_base=True)
        with self.assertRaises(ValidationError):
            tpl.clean()

    def test_clean_rejects_invalid_syntax(self):
        tpl = EmailTemplate(slug='emails/z2.html', name='Z2', subject='{{ title }}',
                            body_html='{% if %}', extends_base=True)
        with self.assertRaises(ValidationError):
            tpl.clean()


class RenderEmailFallbackTests(TestCase):
    def setUp(self):
        # The seed data migration pre-populates templates in the test DB; start
        # from a clean slate so these fallback tests are deterministic.
        EmailTemplate.objects.all().delete()

    def test_db_template_wins_when_active(self):
        EmailTemplate.objects.create(
            slug='emails/test_email.html', name='Test', subject='DB subject',
            body_html='DB body {{ user }}', extends_base=True, is_active=True,
        )
        subject, html, _ = render_email('emails/test_email.html', CTX)
        self.assertEqual(subject, 'DB subject')
        self.assertIn('DB body Alice', html)

    def test_falls_back_to_filesystem_when_inactive(self):
        EmailTemplate.objects.create(
            slug='emails/test_email.html', name='Test', subject='DB subject',
            body_html='DB body', extends_base=True, is_active=False,
        )
        _, html, _ = render_email('emails/test_email.html', CTX)
        self.assertEqual(html, render_to_string('emails/test_email.html', CTX))

    def test_falls_back_when_no_row(self):
        _, html, _ = render_email('emails/test_email.html', CTX)
        self.assertEqual(html, render_to_string('emails/test_email.html', CTX))
