from django.db import migrations


TABLE = "chaotica_utils_user"
COLUMN = "alias"
# VARCHAR(255), matches models.CharField(max_length=255, null=True, blank=True, default="").
# MySQL column syntax requires CHARACTER SET/COLLATE immediately after the type,
# before the NULL/DEFAULT clauses.
ALTER = (
    "ALTER TABLE {table} MODIFY {col} VARCHAR(255) "
    "CHARACTER SET {charset} COLLATE {collation} NULL DEFAULT ''"
)


def to_utf8mb4(apps, schema_editor):
    """Convert the alias column to utf8mb4 so it can store emoji (4-byte chars).

    The legacy user table is utf8mb3, which raises OperationalError (1366)
    on emoji input. Only relevant to MySQL/MariaDB; a no-op elsewhere.
    """
    if schema_editor.connection.vendor != "mysql":
        return
    schema_editor.execute(
        ALTER.format(
            table=TABLE, col=COLUMN,
            charset="utf8mb4", collation="utf8mb4_unicode_ci",
        )
    )


def to_utf8mb3(apps, schema_editor):
    """Revert the alias column to the table's legacy utf8mb3 charset."""
    if schema_editor.connection.vendor != "mysql":
        return
    schema_editor.execute(
        ALTER.format(
            table=TABLE, col=COLUMN,
            charset="utf8mb3", collation="utf8mb3_bin",
        )
    )


class Migration(migrations.Migration):

    # MySQL/MariaDB can't roll back DDL, so run the ALTER outside a transaction.
    atomic = False

    dependencies = [
        ("chaotica_utils", "0034_user_scheduler_default_filter"),
    ]

    operations = [
        migrations.RunPython(to_utf8mb4, to_utf8mb3),
    ]
