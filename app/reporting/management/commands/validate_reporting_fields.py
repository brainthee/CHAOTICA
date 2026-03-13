from django.core.management.base import BaseCommand

from reporting.models import DataArea, DataField


class Command(BaseCommand):
    help = 'Validate all reporting DataField definitions against their actual Django models'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Disable invalid fields automatically',
        )

    def handle(self, *args, **options):
        fix = options['fix']
        total_valid = 0
        total_invalid = 0
        total_warnings = 0
        invalid_fields = []

        data_areas = DataArea.objects.all().prefetch_related('fields__field_type')

        for data_area in data_areas:
            self.stdout.write(f"\n{'=' * 60}")
            self.stdout.write(self.style.HTTP_INFO(
                f"  {data_area.name} ({data_area.content_type.app_label}.{data_area.model_name})"
            ))
            self.stdout.write(f"{'=' * 60}")

            model_class = None
            try:
                model_class = data_area.content_type.model_class()
                if model_class is None:
                    self.stdout.write(self.style.ERROR(
                        f"  Content type does not resolve to a model class."
                    ))
                    continue
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Cannot resolve content type: {e}"))
                continue

            for field in data_area.fields.filter(is_available=True):
                result = _validate_field_path(model_class, field)

                if result['status'] == 'valid':
                    total_valid += 1
                    self.stdout.write(
                        f"  {self.style.SUCCESS('OK')}  {field.display_name:30s} "
                        f"  {field.field_path:30s}  -> {result['resolved_type']}"
                    )
                elif result['status'] == 'warning':
                    total_warnings += 1
                    self.stdout.write(
                        f"  {self.style.WARNING('WARN')}  {field.display_name:30s} "
                        f"  {field.field_path:30s}  {result['error']}"
                    )
                else:
                    total_invalid += 1
                    invalid_fields.append(field)
                    self.stdout.write(
                        f"  {self.style.ERROR('FAIL')}  {field.display_name:30s} "
                        f"  {field.field_path:30s}  {result['error']}"
                    )

        self.stdout.write(f"\n{'=' * 60}")
        self.stdout.write(f"  Summary: {total_valid} valid, {total_warnings} warnings, {total_invalid} invalid")
        self.stdout.write(f"{'=' * 60}")

        if invalid_fields and fix:
            for field in invalid_fields:
                field.is_available = False
                field.save(update_fields=['is_available'])
            self.stdout.write(self.style.SUCCESS(
                f"\n  Disabled {len(invalid_fields)} invalid field(s)."
            ))
        elif invalid_fields and not fix:
            self.stdout.write(self.style.WARNING(
                f"\n  Run with --fix to disable the {len(invalid_fields)} invalid field(s)."
            ))


def _validate_field_path(model_class, data_field):
    """Validate a DataField's field_path against the Django model."""
    field_path = data_field.field_path
    parts = field_path.split('__')
    current_model = model_class
    result = {
        'status': 'valid',
        'error': None,
        'resolved_type': None,
    }

    for part in parts:
        if part.startswith('_'):
            try:
                django_field = current_model._meta.get_field(part)
                result['resolved_type'] = type(django_field).__name__
                if hasattr(django_field, 'related_model') and django_field.related_model:
                    current_model = django_field.related_model
                continue
            except Exception:
                pass

            if hasattr(current_model, part):
                result['status'] = 'warning'
                result['error'] = (
                    f"'{part}' is a property/attribute on {current_model.__name__}, "
                    f"not a DB field."
                )
                return result

            result['status'] = 'invalid'
            available = sorted(f.name for f in current_model._meta.get_fields())
            result['error'] = (
                f"Cannot resolve '{part}' on {current_model.__name__}. "
                f"Available: {', '.join(available[:15])}"
            )
            return result

        try:
            django_field = current_model._meta.get_field(part)
            result['resolved_type'] = type(django_field).__name__
            if hasattr(django_field, 'related_model') and django_field.related_model:
                current_model = django_field.related_model
        except Exception:
            if hasattr(current_model, part):
                result['status'] = 'warning'
                result['error'] = (
                    f"'{part}' is an attribute on {current_model.__name__}, not a DB field."
                )
                return result

            result['status'] = 'invalid'
            available = sorted(f.name for f in current_model._meta.get_fields())
            result['error'] = (
                f"Cannot resolve '{part}' on {current_model.__name__}. "
                f"Available: {', '.join(available[:15])}"
            )
            return result

    return result
