"""
Management command to profile DB query counts on known N+1 hotspot views.

Usage:
    python manage.py profile_views --user user@example.com

Run before and after an optimisation to measure the delta.
"""

import re
import time
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext, override_settings
from django.urls import reverse


class Command(BaseCommand):
    help = "Profile DB query counts for known N+1 hotspot views"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            required=True,
            help="Email address of the user to authenticate as",
        )

    @staticmethod
    def _normalize_sql(sql):
        """Strip literal values so equivalent N+1 queries group together."""
        sql = re.sub(r"'[^']*'", "?", sql)
        sql = re.sub(r"\b\d+\b", "?", sql)
        return sql

    def handle(self, *args, **options):
        from django.contrib.auth import get_user_model
        from django.db import models

        from jobtracker.models import Job, Phase

        User = get_user_model()

        try:
            auth_user = User.objects.get(email=options["user"])
        except User.DoesNotExist:
            raise CommandError(f"No user with email: {options['user']}")

        # Find a job that has at least one phase, for phase_detail and
        # create_scheduler_phase_slot profiling.
        job = Job.objects.filter(phases__isnull=False).first()
        phase = Phase.objects.filter(job=job).first() if job else None

        date_range = {"start": "2026-01-01T00:00:00", "end": "2026-04-01T00:00:00"}

        urls = [
            ("scheduler/members", reverse("view_scheduler_members"), {}),
            ("scheduler/timeslots", reverse("view_scheduler_slots"), date_range),
            (
                "profile/update",
                reverse("update_profile", kwargs={"email": auth_user.email}),
                {},
            ),
            (
                "profile/update/skills",
                reverse("update_skills", kwargs={"email": auth_user.email}),
                {},
            ),
        ]

        if job and phase:
            urls.append((
                "phase/detail",
                reverse(
                    "phase_detail",
                    kwargs={"job_slug": str(job.slug), "slug": phase.slug},
                ),
                {},
            ))
            urls.append((
                "scheduler/phase/create",
                reverse("create_scheduler_phase_slot"),
                {"job": job.pk, "phase": phase.pk, "start": "2026-01-06T09:00:00Z", "end": "2026-01-06T17:00:00Z"},
            ))
            # Profile a job detail page — pick the job with the most phases for a realistic load.
            heavy_job = Job.objects.annotate(
                phase_count=models.Count('phases')
            ).order_by('-phase_count').first()
            if heavy_job:
                urls.append((
                    "job/detail (heavy)",
                    reverse("job_detail", kwargs={"slug": str(heavy_job.slug)}),
                    {},
                ))
        else:
            self.stderr.write(self.style.WARNING(
                "No job with phases found — skipping phase_detail and create_scheduler_phase_slot"
            ))

        client = Client()
        client.force_login(auth_user)

        col_view = 32
        col_q = 9
        col_t = 11
        col_r = 10
        header = (
            f"{'View':<{col_view}} {'Queries':>{col_q}} {'DB time':>{col_t}} "
            f"{'Wasted':>{col_r}}  Top repeated pattern"
        )
        rule = "─" * 100

        self.stdout.write(f"\n{rule}")
        self.stdout.write(header)
        self.stdout.write(rule)

        with override_settings(DEBUG=True, ALLOWED_HOSTS=["*"]):
            for label, url, params in urls:
                try:
                    with CaptureQueriesContext(connection) as ctx:
                        response = client.get(url, params, HTTP_HOST="localhost")
                except Exception as exc:
                    self.stdout.write(
                        f"{label:<{col_view}} {'ERROR':>{col_q}}             "
                        f"             {type(exc).__name__}: {exc}"
                    )
                    continue

                queries = list(ctx)
                query_count = len(queries)
                db_ms = sum(float(q["time"]) for q in queries) * 1000

                norm_counter = Counter(self._normalize_sql(q["sql"]) for q in queries)
                unique_patterns = len(norm_counter)
                wasted = sum(cnt - 1 for cnt in norm_counter.values() if cnt > 1)

                status = response.status_code
                status_tag = f" [{status}]" if status != 200 else ""

                top_repeat = ""
                if wasted > 0:
                    top_sql, top_cnt = norm_counter.most_common(1)[0]
                    top_repeat = f"x{top_cnt}: {top_sql[:60]}"

                self.stdout.write(
                    f"{label + status_tag:<{col_view}} "
                    f"{query_count:>{col_q}} "
                    f"{db_ms:>{col_t-2}.1f} ms "
                    f"{wasted:>{col_r}}  {top_repeat}"
                )

        self.stdout.write(rule)
        self.stdout.write(
            "\nWasted = duplicate query executions that a prefetch would eliminate.\n"
        )
