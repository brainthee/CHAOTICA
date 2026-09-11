"""Convert MySQL tables from utf8mb3 to utf8mb4 so 4-byte characters (emoji, etc.)
are storable.

Some environments were created when the server default was ``utf8`` (an alias for
the 3-byte ``utf8mb3``). Those columns raise ``OperationalError 1366 "Incorrect
string value"`` on a 4-byte char (e.g. an emoji in a user's name flowing into an
AuditEvent message), which poisons the transaction. Django's connection already
speaks utf8mb4 and the database default is utf8mb4 — only the *existing tables*
need converting.

Each table is converted **preserving its collation family** (``utf8mb3_bin`` →
``utf8mb4_bin``) so only the byte width changes: no case-sensitivity change, no
new cross-collation join risk. Idempotent (only touches non-utf8mb4 tables).
Dry-run by default; pass ``--force`` to apply.

DDL locks tables while it runs — schedule a maintenance window on large/prod DBs.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

TARGET_CHARSET = "utf8mb4"
DEFAULT_COLLATION = "utf8mb4_bin"


class Command(BaseCommand):
    help = (
        "Convert MySQL tables from utf8mb3 to utf8mb4 (preserving binary collation) "
        "so 4-byte characters are storable. Dry-run unless --force."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true", help="Apply the ALTERs (otherwise dry-run)."
        )
        parser.add_argument(
            "--collation",
            default=DEFAULT_COLLATION,
            help="Target collation (default utf8mb4_bin — preserves binary comparison).",
        )

    def handle(self, *args, **options):
        if connection.vendor != "mysql":
            raise CommandError("This command only applies to MySQL/MariaDB.")

        collation = options["collation"]
        with connection.cursor() as cur:
            cur.execute("SELECT DATABASE()")
            db = cur.fetchone()[0]

            cur.execute(
                """
                SELECT t.table_name, ccsa.character_set_name
                FROM information_schema.tables t
                JOIN information_schema.collation_character_set_applicability ccsa
                  ON ccsa.collation_name = t.table_collation
                WHERE t.table_schema = %s
                  AND t.table_type = 'BASE TABLE'
                  AND ccsa.character_set_name <> %s
                ORDER BY t.table_name
                """,
                [db, TARGET_CHARSET],
            )
            rows = cur.fetchall()

            if not rows:
                self.stdout.write(
                    self.style.SUCCESS(
                        "All base tables in '{}' are already {}. Nothing to do.".format(
                            db, TARGET_CHARSET
                        )
                    )
                )
                return

            self.stdout.write(
                "{} table(s) in '{}' to convert to {} COLLATE {}:".format(
                    len(rows), db, TARGET_CHARSET, collation
                )
            )

            if not options["force"]:
                for name, cs in rows:
                    self.stdout.write("  {}  (currently {})".format(name, cs))
                self.stdout.write(
                    self.style.WARNING("Dry run — re-run with --force to apply.")
                )
                return

            # Make the database default utf8mb4 too (so future tables inherit it).
            cur.execute(
                "ALTER DATABASE `{}` CHARACTER SET {} COLLATE {}".format(
                    db, TARGET_CHARSET, collation
                )
            )

            converted = 0
            failed = []
            for name, _cs in rows:
                try:
                    cur.execute(
                        "ALTER TABLE `{}` CONVERT TO CHARACTER SET {} COLLATE {}".format(
                            name, TARGET_CHARSET, collation
                        )
                    )
                    converted += 1
                    self.stdout.write(self.style.SUCCESS("  converted {}".format(name)))
                except Exception as exc:  # noqa: BLE001 - report and continue
                    failed.append((name, str(exc)))
                    self.stderr.write(self.style.ERROR("  FAILED {}: {}".format(name, exc)))

            self.stdout.write(
                self.style.SUCCESS("Converted {} table(s) to {}.".format(converted, TARGET_CHARSET))
            )
            if failed:
                self.stdout.write(
                    self.style.WARNING(
                        "{} table(s) failed (see errors above) — likely an index-length "
                        "limit; convert those columns individually.".format(len(failed))
                    )
                )
