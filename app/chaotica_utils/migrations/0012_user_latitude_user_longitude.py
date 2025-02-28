# Generated by Django 5.0.6 on 2024-10-25 10:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chaotica_utils", "0011_alter_leaverequest_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="latitude",
            field=models.DecimalField(
                blank=True, decimal_places=16, max_digits=22, null=True
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="longitude",
            field=models.DecimalField(
                blank=True, decimal_places=16, max_digits=22, null=True
            ),
        ),
    ]
