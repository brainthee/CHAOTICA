from django.db import models
from django.conf import settings
from django.utils import timezone
from jobtracker.models import Phase
from chaotica_utils.models import User, get_sentinel_user
import uuid


class QAReviewManager(models.Manager):
    def get_random_eligible_users(self, weeks_back=4, unit=None):
        from jobtracker.models import Phase, Job
        from jobtracker.enums import PhaseStatuses
        from django.db.models import Q
        import random
        from datetime import timedelta

        cutoff_date = timezone.now() - timedelta(weeks=weeks_back)

        query = Q(
            phases__status__in=[PhaseStatuses.COMPLETED, PhaseStatuses.DELIVERED],  # Completed phases
            phases__linkDeliverable__isnull=False
        ) & Q(
            phases__linkDeliverable__gt=''
        ) & Q(
            phases__status_changed_date__gte=cutoff_date  # Use status change date
        )

        if unit:
            query &= Q(phases__job__unit=unit)

        eligible_users = User.objects.filter(query).distinct()
        return eligible_users


class QAReview(models.Model):
    REVIEW_STATUS_CHOICES = [
        ('started', 'Started'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phase = models.ForeignKey(
        Phase,
        on_delete=models.CASCADE,
        related_name='qa_reviews'
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET(get_sentinel_user),
        related_name='qa_reviews_conducted'
    )
    reviewed_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET(get_sentinel_user),
        related_name='qa_reviews_received'
    )

    status = models.CharField(
        max_length=20,
        choices=REVIEW_STATUS_CHOICES,
        default='started'
    )

    weeks_back_config = models.IntegerField(
        default=4,
        help_text="Number of weeks back used for selection"
    )

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    notes = models.TextField(
        blank=True,
        help_text="Review notes and feedback"
    )

    objects = QAReviewManager()

    class Meta:
        ordering = ['-started_at']
        verbose_name = 'QA Review'
        verbose_name_plural = 'QA Reviews'

    def __str__(self):
        return f"QA Review of {self.phase.phase_id} by {self.reviewer}"

    def complete_review(self):
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save()

    def abort_review(self):
        self.status = 'cancelled'
        self.completed_at = timezone.now()  # Track when it was cancelled
        self.save()

    def can_be_aborted_by(self, user):
        """Check if a user can abort this review"""
        return user == self.reviewer or user.is_staff or user.is_superuser

    def can_be_completed_by(self, user):
        """Check if a user can complete this review"""
        return user == self.reviewer


class QAReviewConfiguration(models.Model):
    unit = models.ForeignKey(
        'jobtracker.OrganisationalUnit',
        on_delete=models.CASCADE,
        related_name='qa_config'
    )
    weeks_back = models.IntegerField(
        default=4,
        help_text="Number of weeks to look back for eligible reports"
    )
    enabled = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'QA Review Configuration'
        verbose_name_plural = 'QA Review Configurations'

    def __str__(self):
        return f"QA Config for {self.unit.name}"
