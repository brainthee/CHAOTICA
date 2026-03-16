from django.test import TestCase

from chaotica_utils.models import User
from jobtracker.enums import QualificationStatus
from jobtracker.forms import AwardingBodyForm, OwnQualificationRecordForm, QualificationForm
from jobtracker.models import AwardingBody, Qualification, QualificationRecord


class OwnQualificationRecordFormTests(TestCase):
    def setUp(self):
        self.body = AwardingBody.objects.create(name="CREST")
        self.qual = Qualification.objects.create(
            awarding_body=self.body, name="CRT", short_name="CRT", validity_period=1095
        )
        self.user = User.objects.create_user(email="user@test.com", password="testpass123")

    def test_form_valid_new_record(self):
        form = OwnQualificationRecordForm(data={
            "qualification": self.qual.pk,
            "status": QualificationStatus.IN_PROGRESS,
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_status_choices_new_record(self):
        form = OwnQualificationRecordForm()
        status_values = [val for val, _ in form.fields["status"].choices]
        self.assertIn(QualificationStatus.UNKNOWN, status_values)
        self.assertIn(QualificationStatus.IN_PROGRESS, status_values)
        self.assertNotIn(QualificationStatus.AWARDED, status_values)

    def test_form_status_choices_in_progress(self):
        record = QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.IN_PROGRESS,
        )
        form = OwnQualificationRecordForm(instance=record)
        status_values = [val for val, _ in form.fields["status"].choices]
        self.assertIn(QualificationStatus.IN_PROGRESS, status_values)
        self.assertIn(QualificationStatus.PENDING, status_values)
        self.assertIn(QualificationStatus.ATTEMPTED, status_values)
        self.assertIn(QualificationStatus.UNSUCCESSFUL, status_values)

    def test_form_status_choices_attempted(self):
        record = QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.ATTEMPTED,
        )
        form = OwnQualificationRecordForm(instance=record)
        status_values = [val for val, _ in form.fields["status"].choices]
        self.assertIn(QualificationStatus.ATTEMPTED, status_values)
        self.assertIn(QualificationStatus.AWARDED, status_values)
        self.assertIn(QualificationStatus.UNSUCCESSFUL, status_values)

    def test_form_status_choices_awarded(self):
        record = QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.AWARDED,
        )
        form = OwnQualificationRecordForm(instance=record)
        status_values = [val for val, _ in form.fields["status"].choices]
        self.assertEqual(status_values, [QualificationStatus.AWARDED])

    def test_form_status_choices_lapsed(self):
        record = QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.LAPSED,
        )
        form = OwnQualificationRecordForm(instance=record)
        status_values = [val for val, _ in form.fields["status"].choices]
        self.assertIn(QualificationStatus.LAPSED, status_values)
        self.assertIn(QualificationStatus.IN_PROGRESS, status_values)

    def _get_layout_field_names(self, form):
        """Extract field names from the crispy layout."""
        fields = []
        from crispy_forms.layout import Field
        from crispy_forms.utils import flatatt

        def _walk(layout_obj):
            if hasattr(layout_obj, 'fields'):
                for f in layout_obj.fields:
                    if isinstance(f, str):
                        fields.append(f)
                    else:
                        _walk(f)
        _walk(form.helper.layout)
        return fields

    def test_form_hides_awarded_fields_for_early_status(self):
        """For IN_PROGRESS, awarded-specific fields should not be in layout."""
        record = QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.IN_PROGRESS,
        )
        form = OwnQualificationRecordForm(instance=record)
        layout_fields = self._get_layout_field_names(form)
        self.assertNotIn("awarded_date", layout_fields)
        self.assertNotIn("lapse_date", layout_fields)
        self.assertNotIn("certificate_number", layout_fields)

    def test_form_shows_awarded_fields_for_attempted(self):
        """ATTEMPTED can transition to AWARDED, so awarded fields should appear."""
        record = QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.ATTEMPTED,
        )
        form = OwnQualificationRecordForm(instance=record)
        layout_fields = self._get_layout_field_names(form)
        self.assertIn("awarded_date", layout_fields)
        self.assertIn("lapse_date", layout_fields)
        self.assertIn("certificate_number", layout_fields)

    def test_form_shows_all_fields_for_awarded_status(self):
        record = QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.AWARDED,
        )
        form = OwnQualificationRecordForm(instance=record)
        layout_fields = self._get_layout_field_names(form)
        self.assertIn("awarded_date", layout_fields)
        self.assertIn("certificate_file", layout_fields)


class QualificationFormTests(TestCase):
    def setUp(self):
        self.body = AwardingBody.objects.create(name="CREST")

    def test_form_valid(self):
        form = QualificationForm(data={
            "name": "CRT",
            "short_name": "CRT",
            "validity_period": 1095,
            "description": "",
            "verification_required": True,
            "url": "",
            "guidance_url": "",
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_fields(self):
        form = QualificationForm()
        self.assertIn("verification_required", form.fields)
        self.assertIn("name", form.fields)
        self.assertIn("validity_period", form.fields)


class AwardingBodyFormTests(TestCase):
    def test_form_valid(self):
        form = AwardingBodyForm(data={
            "name": "CREST",
            "description": "Test body",
            "url": "https://example.com",
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_fields(self):
        form = AwardingBodyForm()
        self.assertIn("name", form.fields)
        self.assertIn("description", form.fields)
        self.assertIn("url", form.fields)
        self.assertIn("logo", form.fields)
