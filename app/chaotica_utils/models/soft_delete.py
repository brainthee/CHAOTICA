"""Reusable soft-delete support.

Models that mix in :class:`SoftDeleteModel` gain an ``is_deleted`` flag and a
default manager (``objects``) that hides deleted rows, so existing queries stop
returning them automatically. ``all_objects`` remains for admin / restore /
historical access, and — crucially — is wired as the model's *base* manager so
related-object access (e.g. ``job.client`` on a job whose client was
soft-deleted) still resolves. That is the whole point of soft-deleting these
records instead of hard-deleting them: the dependent jobs/phases/history must
survive intact.
"""

from django.db import models
from django.utils import timezone


class ActiveManager(models.Manager):
    """Default manager that excludes soft-deleted rows."""

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class SoftDeleteModel(models.Model):
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_date = models.DateTimeField(null=True, blank=True)

    # NB: declare the filtering manager first so it becomes the default manager.
    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def soft_delete(self, user=None):
        self.is_deleted = True
        self.deleted_date = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_date"])

    def restore(self):
        self.is_deleted = False
        self.deleted_date = None
        self.save(update_fields=["is_deleted", "deleted_date"])
