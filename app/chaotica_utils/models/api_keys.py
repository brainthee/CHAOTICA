import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone


class HealthCheckAPIKey(models.Model):
    """API Key for health check endpoint authentication"""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='health_check_api_key'
    )
    key = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Health Check API Key"
        verbose_name_plural = "Health Check API Keys"
        ordering = ['-created_at']

    def __str__(self):
        return f"API Key for {self.user.email}"

    def regenerate_key(self):
        """Generate a new API key"""
        self.key = uuid.uuid4()
        self.created_at = timezone.now()
        self.save()
        return self.key

    def mark_used(self):
        """Update last used timestamp"""
        self.last_used = timezone.now()
        self.save(update_fields=['last_used'])

    @classmethod
    def get_or_create_for_user(cls, user):
        """Get or create an API key for a user"""
        api_key, created = cls.objects.get_or_create(
            user=user,
            defaults={'is_active': True}
        )
        return api_key