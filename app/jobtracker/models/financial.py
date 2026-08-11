from django.conf import settings
from django.db import models
from django.urls import reverse
from django.db.models.functions import Lower
from django.db.models import Q
from django_countries.fields import CountryField
from django.template.loader import render_to_string


class BillingCodeManager(models.Manager):
    def for_user(self, user):
        """Billing codes ``user`` can reach.

        Closes the prior exposure gap where every authenticated user could see
        every client's codes. A user reaches:

        * client-less (internal / shared) codes, and
        * codes whose client has a job in an organisational unit the user can
          view jobs in.

        Superusers see everything.
        """
        qs = self.get_queryset()
        if not user.is_authenticated:
            return qs.none()
        if user.is_superuser:
            return qs
        from guardian.shortcuts import get_objects_for_user
        from .orgunit import OrganisationalUnit

        units = get_objects_for_user(
            user, "jobtracker.can_view_jobs", klass=OrganisationalUnit
        )
        return qs.filter(
            Q(client__isnull=True) | Q(client__jobs__unit__in=units)
        ).distinct()


class BillingCode(models.Model):
    objects = BillingCodeManager()

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

        job_ids = self.assignments.filter(job__isnull=False).values_list(
            "job_id", flat=True
        )
        return Job.objects.filter(id__in=job_ids)

    def phases(self):
        from ..models import Phase

        phase_ids = self.assignments.filter(phase__isnull=False).values_list(
            "phase_id", flat=True
        )
        return Phase.objects.filter(id__in=phase_ids)

    def projects(self):
        from ..models import Project

        project_ids = self.assignments.filter(project__isnull=False).values_list(
            "project_id", flat=True
        )
        return Project.objects.filter(id__in=project_ids)

    class Meta:
        ordering = [Lower("code")]

    def get_absolute_url(self):
        return reverse("billingcode_detail", kwargs={"code": self.code})


class BillingCodeAssignment(models.Model):
    """A dated link between a :class:`BillingCode` and a job, phase or project.

    Exactly one of ``job`` / ``phase`` / ``project`` is set (enforced by a
    CheckConstraint). The optional ``start_date`` / ``end_date`` describe *when*
    the code applies to that target:

    * both ``None`` — the code applies for the whole target span (an "undated"
      assignment);
    * one bound ``None`` — open-ended on that side;
    * both set — a closed range (``start <= day <= end``).

    Multiple dated assignments of the same code to the same target may coexist
    (e.g. a code replaced mid-engagement, the old one kept for historical
    dates). Phases inherit their job's assignments unless they have their own
    (see :meth:`Phase.get_effective_billing_assignments`).
    """

    code = models.ForeignKey(
        BillingCode,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    job = models.ForeignKey(
        "Job",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="billing_code_assignments",
    )
    phase = models.ForeignKey(
        "Phase",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="billing_code_assignments",
    )
    project = models.ForeignKey(
        "Project",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="billing_code_assignments",
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        indexes = [
            models.Index(fields=["job"]),
            models.Index(fields=["phase"]),
            models.Index(fields=["project"]),
            models.Index(fields=["code"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="billingcodeassignment_exactly_one_target",
                check=(
                    Q(job__isnull=False, phase__isnull=True, project__isnull=True)
                    | Q(job__isnull=True, phase__isnull=False, project__isnull=True)
                    | Q(job__isnull=True, phase__isnull=True, project__isnull=False)
                ),
            ),
            models.CheckConstraint(
                name="billingcodeassignment_valid_date_range",
                check=(
                    Q(end_date__isnull=True)
                    | Q(start_date__isnull=True)
                    | Q(end_date__gte=models.F("start_date"))
                ),
            ),
            models.UniqueConstraint(
                fields=["code", "job", "phase", "project", "start_date", "end_date"],
                name="billingcodeassignment_unique_target_range",
            ),
        ]

    @property
    def target(self):
        return self.job or self.phase or self.project

    def __str__(self):
        span = ""
        if self.start_date or self.end_date:
            span = " ({} → {})".format(
                self.start_date or "…", self.end_date or "…"
            )
        return "{}{}".format(self.code, span)
