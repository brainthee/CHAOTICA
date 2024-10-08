# Generated by Django 5.0.6 on 2024-08-28 13:01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "jobtracker",
            "0016_historicalproject_project_historicaltimeslot_project_and_more",
        ),
    ]

    operations = [
        migrations.AlterField(
            model_name="historicalproject",
            name="status",
            field=models.IntegerField(
                choices=[
                    (0, "Untracked"),
                    (1, "Pending"),
                    (2, "In Progress"),
                    (3, "Complete"),
                ],
                default=0,
                help_text="Current state of the job",
                verbose_name="Job Status",
            ),
        ),
        migrations.AlterField(
            model_name="project",
            name="status",
            field=models.IntegerField(
                choices=[
                    (0, "Untracked"),
                    (1, "Pending"),
                    (2, "In Progress"),
                    (3, "Complete"),
                ],
                default=0,
                help_text="Current state of the job",
                verbose_name="Job Status",
            ),
        ),
    ]
