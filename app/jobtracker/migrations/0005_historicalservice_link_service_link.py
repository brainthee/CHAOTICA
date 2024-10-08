# Generated by Django 5.0.6 on 2024-08-19 15:01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobtracker", "0004_historicalservice_description_service_description"),
    ]

    operations = [
        migrations.AddField(
            model_name="historicalservice",
            name="link",
            field=models.URLField(
                blank=True,
                default="",
                max_length=2000,
                null=True,
                verbose_name="Link to service information",
            ),
        ),
        migrations.AddField(
            model_name="service",
            name="link",
            field=models.URLField(
                blank=True,
                default="",
                max_length=2000,
                null=True,
                verbose_name="Link to service information",
            ),
        ),
    ]
