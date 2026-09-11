"""Rename support profile ``weight`` (1.0/0.2) to a plain percentage (100/20).

Users think in percentages, not weights, so the field is presented and stored as
a percent. The share maths (percent / Σ percents) is a ratio, so the numbers are
unchanged. Any existing dev rows are converted ×100.
"""

from decimal import Decimal

from django.db import migrations, models


def weight_to_percent(apps, schema_editor):
    for model_name in (
        "JobSupportTeamRole",
        "OrganisationalUnitSupportTemplateMember",
    ):
        Model = apps.get_model("jobtracker", model_name)
        for row in Model.objects.all():
            if row.profile_percent is not None:
                row.profile_percent = row.profile_percent * Decimal("100")
                row.save(update_fields=["profile_percent"])


def percent_to_weight(apps, schema_editor):
    for model_name in (
        "JobSupportTeamRole",
        "OrganisationalUnitSupportTemplateMember",
    ):
        Model = apps.get_model("jobtracker", model_name)
        for row in Model.objects.all():
            if row.profile_percent is not None:
                row.profile_percent = row.profile_percent / Decimal("100")
                row.save(update_fields=["profile_percent"])


class Migration(migrations.Migration):

    dependencies = [
        ("jobtracker", "0079_alter_organisationalunit_options_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="jobsupportteamrole",
            old_name="profile_weight",
            new_name="profile_percent",
        ),
        migrations.RenameField(
            model_name="historicaljobsupportteamrole",
            old_name="profile_weight",
            new_name="profile_percent",
        ),
        migrations.RenameField(
            model_name="organisationalunitsupporttemplatemember",
            old_name="profile_weight",
            new_name="profile_percent",
        ),
        migrations.RenameField(
            model_name="historicalorganisationalunitsupporttemplatemember",
            old_name="profile_weight",
            new_name="profile_percent",
        ),
        migrations.AlterField(
            model_name="jobsupportteamrole",
            name="profile_percent",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("100"),
                help_text="Coverage % (100 = full coverage). Drives this person's share of the support pool.",
                max_digits=6,
                verbose_name="Profile Allocation (%)",
            ),
        ),
        migrations.AlterField(
            model_name="historicaljobsupportteamrole",
            name="profile_percent",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("100"),
                help_text="Coverage % (100 = full coverage). Drives this person's share of the support pool.",
                max_digits=6,
                verbose_name="Profile Allocation (%)",
            ),
        ),
        migrations.AlterField(
            model_name="organisationalunitsupporttemplatemember",
            name="profile_percent",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("100"),
                help_text="Coverage % (100 = full coverage). Drives this person's share of the support pool.",
                max_digits=6,
                verbose_name="Profile Allocation (%)",
            ),
        ),
        migrations.AlterField(
            model_name="historicalorganisationalunitsupporttemplatemember",
            name="profile_percent",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("100"),
                help_text="Coverage % (100 = full coverage). Drives this person's share of the support pool.",
                max_digits=6,
                verbose_name="Profile Allocation (%)",
            ),
        ),
        migrations.RunPython(weight_to_percent, percent_to_weight),
    ]
