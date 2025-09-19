from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError


class JobLevel(models.Model):
    """Career levels/grades within the organization"""

    short_label = models.CharField(
        max_length=10,
        unique=True,
        help_text="Short identifier (e.g., 'JL1', 'JL2')"
    )
    long_label = models.CharField(
        max_length=100,
        null=True, blank=True,
        help_text="Full description (e.g., 'Job Level 1 - Senior Manager')"
    )
    order = models.PositiveIntegerField(
        unique=True,
        help_text="Sort order (lower numbers have priority)"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this level is currently in use"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Job Level"
        verbose_name_plural = "Job Levels"
        ordering = ['order']

    def __str__(self):
        if self.long_label:
            return f"{self.short_label} - {self.long_label}"
        else:
            return f"{self.short_label}"

    def clean(self):
        # Ensure order is positive
        if self.order is not None and self.order <= 0:
            raise ValidationError("Order must be a positive number")

    @classmethod
    def get_next_order(cls):
        """Get the next available order number"""
        last_order = cls.objects.aggregate(
            max_order=models.Max('order')
        )['max_order']
        return (last_order or 0) + 1


class UserJobLevel(models.Model):
    """Track user job level assignments and promotions"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='job_level_history'
    )
    job_level = models.ForeignKey(
        JobLevel,
        on_delete=models.CASCADE,
        related_name='user_assignments'
    )
    assigned_date = models.DateField(
        default=timezone.now,
        help_text="Date when this level was assigned"
    )
    is_current = models.BooleanField(
        default=True,
        help_text="Whether this is the user's current level"
    )
    notes = models.TextField(
        blank=True,
        help_text="Optional notes about the assignment/promotion"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "User Job Level"
        verbose_name_plural = "User Job Levels"
        ordering = ['-assigned_date', '-created_at']
        indexes = [
            models.Index(fields=['user', 'is_current']),
            models.Index(fields=['assigned_date']),
        ]

    def __str__(self):
        status = "Current" if self.is_current else "Previous"
        return f"{self.user.email} - {self.job_level.short_label} ({status})"

    def clean(self):
        # Ensure assigned_date is not in the future
        if self.assigned_date and self.assigned_date > timezone.now().date():
            raise ValidationError("Assignment date cannot be in the future")

    def save(self, *args, **kwargs):
        # If this is being set as current, unset other current levels for this user
        if self.is_current:
            UserJobLevel.objects.filter(
                user=self.user,
                is_current=True
            ).exclude(pk=self.pk).update(is_current=False)

        super().save(*args, **kwargs)

    @classmethod
    def get_current_level(cls, user):
        """Get the current job level for a user"""
        try:
            return cls.objects.filter(
                user=user,
                is_current=True
            ).select_related('job_level').first()
        except cls.DoesNotExist:
            return None

    @classmethod
    def assign_level(cls, user, job_level, assigned_date=None, notes=""):
        """Assign a new job level to a user"""
        if assigned_date is None:
            assigned_date = timezone.now().date()

        # Create the new assignment
        return cls.objects.create(
            user=user,
            job_level=job_level,
            assigned_date=assigned_date,
            is_current=True,
            notes=notes
        )