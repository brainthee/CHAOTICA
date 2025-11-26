from django.db import models
import uuid
import os
from ..managers import SystemNoteManager
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.conf import settings
from django.contrib.auth import get_user_model
from simple_history.models import HistoricalRecords
from datetime import date
from django.db.models.functions import Lower
from django_countries.fields import CountryField
from ..utils import get_sentinel_user


class Quote(models.Model):
    create_date = models.DateTimeField(
        verbose_name="Created",
        auto_now_add=True,
        help_text="Date the quote was created",
    )
    mod_date = models.DateTimeField(
        verbose_name="Last Modified",
        auto_now=True,
        help_text="Date the quote was last modified",
    )
    content = models.TextField(verbose_name="Content", help_text="Note Text")
    author = models.CharField(verbose_name="Author", max_length=255, help_text="Author")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET(get_sentinel_user),
    )

    enabled = models.BooleanField(
        verbose_name="Enabled",
        help_text="Enabled for showing",
        default=True,
    )

    class Meta:
        verbose_name = "Quote"
        verbose_name_plural = "Quotes"
        ordering = ["-create_date"]

    def __str__(self):
        return "{} - {}".format(self.author, self.content)
