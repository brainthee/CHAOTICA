# Generated by Django 5.0.3 on 2024-04-19 14:29

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobtracker", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="organisationalunitrole",
            name="id",
            field=models.BigAutoField(
                auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
            ),
        ),
    ]