from django.db import models
from chaotica_utils.utils import unique_slug_generator
from django.db.models.functions import Lower


class Accreditation(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(null=False, default="", unique=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
        return super().save(*args, **kwargs)

    def __str__(self):
        return "%s" % (self.name)

    class Meta:
        ordering = [Lower("name")]
        unique_together = (("name"),)
        permissions = (("view_users_accreditations", "View Users with Accreditation"),)
