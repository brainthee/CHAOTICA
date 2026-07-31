"""Backfill the default ("User") global role onto users that have none.

Global roles are Django groups prefixed with ``settings.GLOBAL_GROUP_PREFIX``. A user
with no such group has no site-wide access at all — which is how the RM import used to
leave every account it created. This command finds those users and grants them the
default role so they can at least log in and use the site.

    python manage.py grant_default_global_role            # apply
    python manage.py grant_default_global_role --dry-run  # preview only
    python manage.py grant_default_global_role --include-inactive
"""

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from chaotica_utils.enums import GlobalRoles
from chaotica_utils.models import User


class Command(BaseCommand):
    help = "Grant the default 'User' global role to any user that has no global role."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List affected users without making changes.",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Also grant to is_active=False users (default: active only).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        name = settings.GLOBAL_GROUP_PREFIX + dict(GlobalRoles.CHOICES).get(
            GlobalRoles.DEFAULT_ROLE, "User"
        )
        default_group = Group.objects.filter(name=name).first()
        if default_group is None:
            raise CommandError(
                f"Default global-role group {name!r} does not exist. "
                "Has the app been initialised (see chaotica_utils/apps.py)?"
            )

        # Users with no group whose name is a global role.
        qs = User.objects.exclude(
            groups__name__startswith=settings.GLOBAL_GROUP_PREFIX
        )
        if not options["include_inactive"]:
            qs = qs.filter(is_active=True)
        qs = qs.order_by("email").distinct()

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS("No users are missing a global role."))
            return

        self.stdout.write(
            f"{total} user(s) have no global role; granting {name!r}"
            + (" (dry run)" if dry_run else "")
            + ":"
        )
        granted = 0
        for user in qs:
            self.stdout.write(f"  {user.email}")
            if not dry_run:
                user.groups.add(default_group)
                granted += 1

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"\nDry run — would grant to {total} user(s).")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"\nGranted {name!r} to {granted} user(s).")
            )
