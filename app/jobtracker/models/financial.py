from django.db import models
from django.conf import settings
from django.db.models import Q
from chaotica_utils.utils import unique_slug_generator
from django.urls import reverse
from simple_history.models import HistoricalRecords
from django.db.models import JSONField
from django_bleach.models import BleachField
from django.db.models.functions import Lower
from django_countries.fields import CountryField
from django.template.loader import render_to_string


class BillingCode(models.Model):
    code = models.CharField(verbose_name="Code", max_length=255, unique=True)
    client = models.ForeignKey(
        "Client",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="billing_codes",
    )
    is_chargeable = models.BooleanField(default=False)
    is_recoverable = models.BooleanField(default=False)
    is_internal = models.BooleanField(default=False)
    is_closed = models.BooleanField(default=False)
    region = CountryField(default="GB")

    def __str__(self):
        if self.client:
            return "{code} ({client})".format(code=self.code, client=self.client)
        else:
            return self.code

    def get_html_label(self):
        rendered = render_to_string(
            "partials/billingcode/billingcode_badge.html", {"billingcode": self}
        )
        return rendered

    def get_state_bscolour(self):
        if self.is_closed:
            return "secondary"
        elif self.is_internal:
            return "info"
        elif self.is_chargeable:
            return "success"
        else:
            return "info"

    def jobs(self):
        from ..models import Job

        if self.associations.all().count():
            assoc_ids = self.associations.filter().values_list("job_id", flat=True)
            return Job.objects.filter(id__in=assoc_ids)
        else:
            return Job.objects.none()

    class Meta:
        ordering = [Lower("code")]

    def get_absolute_url(self):
        return reverse("billingcode_detail", kwargs={"code": self.code})


# class BillingCodeAssociation(models.Model):
#     code = models.ForeignKey(BillingCode, on_delete=models.CASCADE, related_name='associations')
#     job = models.ForeignKey('Job', on_delete=models.CASCADE, related_name='billing_codes')

#     def __str__(self):
#         return self.code.code

#     class Meta:
#         ordering = [Lower('code')]
#         unique_together = ['code', 'job']
