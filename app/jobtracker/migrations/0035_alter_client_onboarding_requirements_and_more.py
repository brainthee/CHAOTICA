# Generated by Django 5.0.6 on 2024-11-15 13:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobtracker", "0034_remove_client_onboarding_reqs_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="client",
            name="onboarding_requirements",
            field=models.TextField(
                blank=True,
                help_text="What requirements are there every renewal.",
                null=True,
                verbose_name="Reoccurring Requirements",
            ),
        ),
        migrations.AlterField(
            model_name="historicalclient",
            name="onboarding_requirements",
            field=models.TextField(
                blank=True,
                help_text="What requirements are there every renewal.",
                null=True,
                verbose_name="Reoccurring Requirements",
            ),
        ),
    ]
