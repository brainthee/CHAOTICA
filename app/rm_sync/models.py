from django.db import models
from django.conf import settings


class RMSyncRecord(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rm_sync_record",
    )
    rm_id = models.CharField(max_length=255, help_text="User ID in Resource Manager")

    last_synced = models.DateTimeField()
    
    sync_enabled = models.BooleanField(default=False, help_text="Should sync schedules")
    remove_non_chaotica = models.BooleanField(default=False, help_text="Removes all non-CHAOTICA time slots. Effectively takes full control.")