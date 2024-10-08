# Generated by Django 5.0.6 on 2024-08-29 23:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobtracker", "0022_alter_historicaljob_external_id_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="historicaljob",
            name="external_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                default=None,
                max_length=255,
                verbose_name="External ID",
            ),
        ),
        migrations.AlterField(
            model_name="job",
            name="external_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                default=None,
                max_length=255,
                unique=True,
                verbose_name="External ID",
            ),
        ),
    ]
