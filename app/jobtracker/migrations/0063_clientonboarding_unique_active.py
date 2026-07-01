from collections import defaultdict

from django.db import migrations, models
from django.utils import timezone


def offboard_duplicate_active_onboardings(apps, schema_editor):
    """Resolve existing duplicates before the partial unique constraint applies.

    For each (user, client) with more than one non-offboarded ClientOnboarding
    row, keep the most-recently-onboarded row active and offboard the rest
    (offboarded = now). Preserves history rather than deleting (BUG-005)."""
    ClientOnboarding = apps.get_model("jobtracker", "ClientOnboarding")

    groups = defaultdict(list)
    for row in ClientOnboarding.objects.filter(offboarded__isnull=True):
        groups[(row.user_id, row.client_id)].append(row)

    now = timezone.now()
    for rows in groups.values():
        if len(rows) < 2:
            continue
        # Rows with an onboarded date sort first; latest onboarded date wins.
        rows.sort(key=lambda r: (r.onboarded is not None, r.onboarded), reverse=True)
        for dup in rows[1:]:
            dup.offboarded = now
            dup.save(update_fields=["offboarded"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("jobtracker", "0062_add_verification_required_to_qualification"),
    ]

    operations = [
        # Dedupe MUST run before the constraint is added.
        migrations.RunPython(offboard_duplicate_active_onboardings, noop),
        migrations.AddConstraint(
            model_name="clientonboarding",
            constraint=models.UniqueConstraint(
                fields=["user", "client"],
                condition=models.Q(offboarded__isnull=True),
                name="unique_active_onboarding_per_user_client",
            ),
        ),
    ]
