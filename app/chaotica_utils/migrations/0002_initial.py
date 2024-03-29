# Generated by Django 5.0.3 on 2024-03-25 18:26

import chaotica_utils.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("chaotica_utils", "0001_initial"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("jobtracker", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="leaverequest",
            name="timeslot",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="jobtracker.timeslot",
            ),
        ),
        migrations.AddField(
            model_name="leaverequest",
            name="user",
            field=models.ForeignKey(
                on_delete=models.SET(chaotica_utils.models.get_sentinel_user),
                related_name="leave_records",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="note",
            name="author",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET(chaotica_utils.models.get_sentinel_user),
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="note",
            name="content_type",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="contenttypes.contenttype",
            ),
        ),
        migrations.AddField(
            model_name="notification",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.AddField(
            model_name="usercost",
            name="user",
            field=models.ForeignKey(
                on_delete=models.SET(chaotica_utils.models.get_sentinel_user),
                related_name="costs",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="userinvitation",
            name="invited_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="users_invited",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="groups",
            field=models.ManyToManyField(
                blank=True,
                help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.",
                related_name="user_set",
                related_query_name="user",
                to="chaotica_utils.group",
                verbose_name="groups",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="holiday",
            unique_together={("date", "country", "reason")},
        ),
        migrations.AlterUniqueTogether(
            name="usercost",
            unique_together={("user", "effective_from")},
        ),
    ]
