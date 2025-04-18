# Generated by Django 5.0.6 on 2025-04-16 10:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0006_notificationsubscription_rule"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="notification_type",
            field=models.IntegerField(
                choices=[
                    (0, "System Notification"),
                    (10, "Job Created"),
                    (11, "Job Status Change"),
                    (12, "Job Pending Scoping"),
                    (13, "Job Pending Scope Signoff"),
                    (14, "Job Scoping Complete"),
                    (29, "Job Complete"),
                    (31, "Phase Status Change"),
                    (32, "Phase Late to TQA"),
                    (33, "Phase Late to PQA"),
                    (36, "Phase TQA Updates"),
                    (37, "Phase PQA Updates"),
                    (34, "Phase Late to Delivery"),
                    (35, "Phase Note Added"),
                    (38, "Phase Feedback"),
                    (39, "Phase Pending Scheduling"),
                    (40, "Phase Scheduling Confirmed"),
                    (41, "Phase Ready for Pre-checks"),
                    (42, "Phase Client Not Ready"),
                    (43, "Phase Ready to Begin"),
                    (44, "Phase In Progress"),
                    (45, "Phase Pending TQA"),
                    (46, "Phase Pending PQA"),
                    (47, "Phase Pending Delivery"),
                    (48, "Phase Completed"),
                    (49, "Phase Postponed"),
                    (50, "Phase Prechecks Overdue"),
                    (60, "Leave Submitted"),
                    (61, "Leave Approved"),
                    (62, "Leave Rejected"),
                    (63, "Leave Cancelled"),
                    (70, "Onboarding Renewal Reminders"),
                ],
                default=0,
            ),
        ),
        migrations.AlterField(
            model_name="notificationoptout",
            name="notification_type",
            field=models.IntegerField(
                choices=[
                    (0, "System Notification"),
                    (10, "Job Created"),
                    (11, "Job Status Change"),
                    (12, "Job Pending Scoping"),
                    (13, "Job Pending Scope Signoff"),
                    (14, "Job Scoping Complete"),
                    (29, "Job Complete"),
                    (31, "Phase Status Change"),
                    (32, "Phase Late to TQA"),
                    (33, "Phase Late to PQA"),
                    (36, "Phase TQA Updates"),
                    (37, "Phase PQA Updates"),
                    (34, "Phase Late to Delivery"),
                    (35, "Phase Note Added"),
                    (38, "Phase Feedback"),
                    (39, "Phase Pending Scheduling"),
                    (40, "Phase Scheduling Confirmed"),
                    (41, "Phase Ready for Pre-checks"),
                    (42, "Phase Client Not Ready"),
                    (43, "Phase Ready to Begin"),
                    (44, "Phase In Progress"),
                    (45, "Phase Pending TQA"),
                    (46, "Phase Pending PQA"),
                    (47, "Phase Pending Delivery"),
                    (48, "Phase Completed"),
                    (49, "Phase Postponed"),
                    (50, "Phase Prechecks Overdue"),
                    (60, "Leave Submitted"),
                    (61, "Leave Approved"),
                    (62, "Leave Rejected"),
                    (63, "Leave Cancelled"),
                    (70, "Onboarding Renewal Reminders"),
                ]
            ),
        ),
        migrations.AlterField(
            model_name="notificationsubscription",
            name="notification_type",
            field=models.IntegerField(
                choices=[
                    (0, "System Notification"),
                    (10, "Job Created"),
                    (11, "Job Status Change"),
                    (12, "Job Pending Scoping"),
                    (13, "Job Pending Scope Signoff"),
                    (14, "Job Scoping Complete"),
                    (29, "Job Complete"),
                    (31, "Phase Status Change"),
                    (32, "Phase Late to TQA"),
                    (33, "Phase Late to PQA"),
                    (36, "Phase TQA Updates"),
                    (37, "Phase PQA Updates"),
                    (34, "Phase Late to Delivery"),
                    (35, "Phase Note Added"),
                    (38, "Phase Feedback"),
                    (39, "Phase Pending Scheduling"),
                    (40, "Phase Scheduling Confirmed"),
                    (41, "Phase Ready for Pre-checks"),
                    (42, "Phase Client Not Ready"),
                    (43, "Phase Ready to Begin"),
                    (44, "Phase In Progress"),
                    (45, "Phase Pending TQA"),
                    (46, "Phase Pending PQA"),
                    (47, "Phase Pending Delivery"),
                    (48, "Phase Completed"),
                    (49, "Phase Postponed"),
                    (50, "Phase Prechecks Overdue"),
                    (60, "Leave Submitted"),
                    (61, "Leave Approved"),
                    (62, "Leave Rejected"),
                    (63, "Leave Cancelled"),
                    (70, "Onboarding Renewal Reminders"),
                ],
                verbose_name="Notification Type",
            ),
        ),
        migrations.AlterField(
            model_name="subscriptionrule",
            name="notification_type",
            field=models.IntegerField(
                choices=[
                    (0, "System Notification"),
                    (10, "Job Created"),
                    (11, "Job Status Change"),
                    (12, "Job Pending Scoping"),
                    (13, "Job Pending Scope Signoff"),
                    (14, "Job Scoping Complete"),
                    (29, "Job Complete"),
                    (31, "Phase Status Change"),
                    (32, "Phase Late to TQA"),
                    (33, "Phase Late to PQA"),
                    (36, "Phase TQA Updates"),
                    (37, "Phase PQA Updates"),
                    (34, "Phase Late to Delivery"),
                    (35, "Phase Note Added"),
                    (38, "Phase Feedback"),
                    (39, "Phase Pending Scheduling"),
                    (40, "Phase Scheduling Confirmed"),
                    (41, "Phase Ready for Pre-checks"),
                    (42, "Phase Client Not Ready"),
                    (43, "Phase Ready to Begin"),
                    (44, "Phase In Progress"),
                    (45, "Phase Pending TQA"),
                    (46, "Phase Pending PQA"),
                    (47, "Phase Pending Delivery"),
                    (48, "Phase Completed"),
                    (49, "Phase Postponed"),
                    (50, "Phase Prechecks Overdue"),
                    (60, "Leave Submitted"),
                    (61, "Leave Approved"),
                    (62, "Leave Rejected"),
                    (63, "Leave Cancelled"),
                    (70, "Onboarding Renewal Reminders"),
                ],
                help_text="Notification type this rule applies to",
            ),
        ),
    ]
