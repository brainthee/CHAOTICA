# Generated by Django 5.0.6 on 2025-04-11 14:34

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0005_notificationoptout"),
    ]

    operations = [
        migrations.AddField(
            model_name="notificationsubscription",
            name="rule",
            field=models.ForeignKey(
                blank=True,
                help_text="The rule that created this subscription",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_subscriptions",
                to="notifications.subscriptionrule",
            ),
        ),
    ]
