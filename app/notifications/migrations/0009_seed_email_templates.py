from django.db import migrations


def seed(apps, schema_editor):
    # Import the shared seeder lazily. It uses the real model (fine for a data
    # migration adding rows), reads filesystem templates, and is idempotent.
    try:
        from notifications.seed_email_templates import seed_email_templates
    except Exception:
        return
    try:
        seed_email_templates(force=False)
    except Exception:
        # Never fail a deploy because a template file is missing or unreadable.
        pass


def unseed(apps, schema_editor):
    EmailTemplate = apps.get_model('notifications', 'EmailTemplate')
    EmailTemplate.objects.filter(is_seeded=True, is_customized=False).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0008_emailtemplate'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
