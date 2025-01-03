# Generated by Django 5.0.6 on 2024-11-14 09:38

import django_countries.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("chaotica_utils", "0013_alter_holiday_country_delete_holidaycountry"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="holiday",
            options={"ordering": ["country", "date"]},
        ),
        migrations.AlterField(
            model_name="user",
            name="country",
            field=django_countries.fields.CountryField(
                default="GB",
                help_text="Used to determine which holidays apply.",
                max_length=2,
            ),
        ),
    ]
