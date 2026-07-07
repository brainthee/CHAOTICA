from django.db.models import Q, F, Value, CharField, Count, Sum, Max, Min, Avg
from django.db.models.functions import Concat
from django.contrib.contenttypes.models import ContentType
from django.apps import apps
from django.core.exceptions import PermissionDenied

from ..models import DataArea, DataField, Report, ReportField, ReportFilter, ReportSort
from ..utils.query_builder import build_query_from_report
from ..resolvers import REPORTING_RESOLVERS
from ..permissions import can_view_report

class DataService:
    """
    Service for retrieving data from models for reporting purposes
    """
    
    @staticmethod
    def get_available_data_areas(user):
        """
        Get all data areas available to the user based on permissions
        """
        # Get all available data areas
        data_areas = DataArea.objects.filter(is_available=True)
        
        # Filter based on permissions
        if not user.is_superuser:
            # This is where you'd implement permission checks
            # For now, we'll return all available data areas
            pass
            
        return data_areas
    
    @staticmethod
    def get_data_area_fields(data_area_id, user):
        """
        Get all fields available for a data area, considering permissions
        """
        data_area = DataArea.objects.get(pk=data_area_id)
        fields = data_area.fields.filter(is_available=True)
        
        # Filter sensitive fields based on permissions
        if not user.is_superuser:
            # Remove sensitive fields if user doesn't have the required permission
            restricted_fields = []
            for field in fields:
                if field.is_sensitive and field.requires_permission:
                    if not user.has_perm(field.requires_permission):
                        restricted_fields.append(field.id)
            
            if restricted_fields:
                fields = fields.exclude(id__in=restricted_fields)
                
        return fields.order_by('group', 'name')
    
    @staticmethod
    def get_report_data(report, user, filter_values=None, extra_field_paths=None):
        """
        Execute a report and return the data.

        ``extra_field_paths`` are additional ORM paths to include in each result
        row (keyed by path) without adding them as display columns - used e.g. to
        fetch a grouping key (like an account manager email) for splitting a
        scheduled report into per-recipient slices.
        """
        extra_field_paths = extra_field_paths or []
        # Check if user has permission to run this report. Use the single
        # permission source of truth (permissions.can_view_report) rather than the
        # weaker Report.can_view, so the data path can't be looser than the views.
        if not can_view_report(user, report):
            raise PermissionDenied("You don't have permission to run this report")
        
        # Get the model and queryset
        content_type = report.data_area.content_type
        model = content_type.model_class()
        queryset = model.objects.all()
        
        # Apply permission filters for the data
        queryset = DataService._apply_permission_filter(queryset, report.data_area, user)
        
        # Build the query based on report definition
        queryset = build_query_from_report(queryset, report, filter_values)
        
        # Get the fields to retrieve
        fields = report.get_fields()

        # Apply sorting. Resolver (computed) fields are not real DB columns, so
        # they can't be used in an ORM order_by - skip them here.
        sorts = report.get_sorts()
        if sorts:
            sort_params = []
            for sort in sorts:
                if getattr(sort.data_field, 'source_type', DataField.SOURCE_ORM) == DataField.SOURCE_RESOLVER:
                    continue
                field_path = sort.data_field.field_path
                if sort.direction == 'desc':
                    field_path = f"-{field_path}"
                sort_params.append(field_path)

            if sort_params:
                queryset = queryset.order_by(*sort_params)

        # If the report uses any computed (resolver) fields, we can't rely on
        # .values() - fall back to iterating model instances and resolving each
        # field in Python. Otherwise use the fast ORM path unchanged.
        has_resolver = any(
            getattr(f.data_field, 'source_type', DataField.SOURCE_ORM) == DataField.SOURCE_RESOLVER
            for f in fields
        )
        if has_resolver:
            return DataService._execute_instance_query(queryset, fields, user, extra_field_paths)

        # Execute the query and return the results
        return DataService._execute_query(queryset, fields, user, extra_field_paths)
    
    @staticmethod
    def _apply_permission_filter(queryset, data_area, user):
        """Scope a report queryset down to what ``user`` may see.

        Applies the SAME guardian object-permission model the rest of the app
        enforces (see ``JobManager.jobs_with_unit_permission`` / ``JobListView``):
        a non-privileged user only sees jobs/phases in the organisational units
        they hold ``can_view_jobs`` on, and restricted engagements are always
        excluded on top. Superusers and holders of ``reporting.can_run_all_reports``
        get the intentional cross-org view.
        """
        model_class = queryset.model

        # A model may still define its own bespoke scoping.
        if hasattr(model_class, 'filter_by_user_permissions'):
            return model_class.filter_by_user_permissions(queryset, user)

        # Superusers see everything, restricted engagements included.
        if user and user.is_superuser:
            return queryset

        field_names = {f.name for f in model_class._meta.get_fields()}

        # ``can_run_all_reports`` grants the intentional cross-org view; everyone
        # else is scoped DOWN to the units they may view jobs in, via whatever
        # relation this model has to an org unit (Job.unit / Phase.job / job-owned
        # areas). This is the same guardian model the rest of the app enforces.
        cross_org = bool(user and user.has_perm('reporting.can_run_all_reports'))
        if not cross_org:
            from jobtracker.models import OrganisationalUnit
            from guardian.shortcuts import get_objects_for_user

            units = get_objects_for_user(
                user, 'jobtracker.can_view_jobs', klass=OrganisationalUnit
            )
            if 'unit' in field_names:
                queryset = queryset.filter(unit__in=units)
            elif 'job' in field_names:
                queryset = queryset.filter(job__unit__in=units)
            elif 'phase' in field_names:
                queryset = queryset.filter(phase__job__unit__in=units)
            else:
                # No unit relationship to scope by (e.g. Client / Skill data
                # areas). These are not job-scoped; without a dedicated
                # ``filter_by_user_permissions`` they are restricted to the
                # full-access roles above.
                return queryset.none()

        # Always exclude restricted engagements for non-superusers (including
        # cross-org reporting accounts).
        if 'is_restricted' in field_names:
            queryset = queryset.exclude(is_restricted=True)
        elif 'job' in field_names:
            queryset = queryset.exclude(job__is_restricted=True)
        elif 'phase' in field_names:
            queryset = queryset.exclude(phase__job__is_restricted=True)

        return queryset
    
    @staticmethod
    def _execute_query(queryset, fields, user=None, extra_field_paths=None):
        """
        Execute the query and format the results.
        Supports aggregation: if any field has an aggregation_function set,
        non-aggregated fields become GROUP BY columns via .values(),
        and aggregated fields use .annotate().

        Sensitive fields the ``user`` may not see are redacted to ``None`` (the
        same rule the instance/resolver path applies via ``_field_visible``) so
        the fast ``.values()`` path can't leak protected columns.
        """
        extra_field_paths = extra_field_paths or []
        AGGREGATION_MAP = {
            'count': Count,
            'sum': Sum,
            'avg': Avg,
            'min': Min,
            'max': Max,
        }

        # Separate fields into group-by and aggregated
        group_by_fields = []
        annotations = {}
        has_aggregation = any(
            getattr(field, 'aggregation_function', '') for field in fields
        )

        if has_aggregation:
            for field in fields:
                field_path = field.data_field.field_path
                agg_func = getattr(field, 'aggregation_function', '')
                if agg_func and agg_func in AGGREGATION_MAP:
                    # Create a unique alias for the annotation
                    alias = f"{agg_func}_{field_path}".replace('__', '_')
                    agg_class = AGGREGATION_MAP[agg_func]
                    annotations[alias] = agg_class(field_path)
                else:
                    group_by_fields.append(field_path)

            results = queryset.values(*group_by_fields).annotate(**annotations).order_by()

            # Reorder result keys to match the original field order, redacting
            # sensitive fields the user may not see.
            ordered_results = []
            for row in results:
                ordered_row = {}
                for field in fields:
                    field_path = field.data_field.field_path
                    visible = DataService._field_visible(field.data_field, user)
                    agg_func = getattr(field, 'aggregation_function', '')
                    if agg_func and agg_func in AGGREGATION_MAP:
                        alias = f"{agg_func}_{field_path}".replace('__', '_')
                        ordered_row[alias] = row.get(alias) if visible else None
                    else:
                        ordered_row[field_path] = row.get(field_path) if visible else None
                ordered_results.append(ordered_row)
            return ordered_results
        else:
            # No aggregation — original behaviour (plus any hidden extra paths)
            field_paths = [field.data_field.field_path for field in fields]
            for path in extra_field_paths:
                if path not in field_paths:
                    field_paths.append(path)
            results = list(queryset.values(*field_paths))
            # Redact sensitive columns the user may not see.
            hidden = {
                field.data_field.field_path
                for field in fields
                if not DataService._field_visible(field.data_field, user)
            }
            if hidden:
                for row in results:
                    for key in hidden:
                        if key in row:
                            row[key] = None
            return results

    @staticmethod
    def _field_visible(data_field, user):
        """Whether ``user`` may see this field's value.

        Mirrors the wizard's field filtering (``get_data_area_fields``): a field
        is only hidden when it is flagged sensitive AND declares a required
        permission the user lacks (superusers always pass).
        """
        if data_field.is_sensitive and data_field.requires_permission:
            if user and (user.is_superuser or user.has_perm(data_field.requires_permission)):
                return True
            return False
        return True

    @staticmethod
    def _walk_path(instance, field_path):
        """Resolve an ORM-style ``a__b__c`` path in Python via getattr.

        Reuses the already-fetched (select_related/prefetch_related) objects
        rather than issuing new queries, and tolerates a null anywhere in the
        chain.
        """
        value = instance
        for part in field_path.split('__'):
            if value is None:
                return None
            value = getattr(value, part, None)
        return value

    @staticmethod
    def _execute_instance_query(queryset, fields, user, extra_field_paths=None):
        """Instance-resolution path for reports containing computed fields.

        Applies the union of every used resolver's select_related/prefetch_related
        hints (so the whole result set is fetched without N+1 queries), then
        resolves each field per row: resolver fields via their whitelisted
        callable, ORM fields via a Python getattr walk. Sensitive fields the user
        can't see are redacted to ``None``.
        """
        # Mixing GROUP BY / aggregation with per-instance resolvers is not
        # supported - the two execution models are incompatible.
        if any(getattr(f, 'aggregation_function', '') for f in fields):
            raise ValueError(
                "Aggregation functions cannot be combined with computed (resolver) fields in the same report."
            )

        extra_field_paths = extra_field_paths or []
        display_paths = {f.data_field.field_path for f in fields}

        select_related = set()
        prefetch_related = set()
        for f in fields:
            if getattr(f.data_field, 'source_type', DataField.SOURCE_ORM) == DataField.SOURCE_RESOLVER:
                resolver = REPORTING_RESOLVERS.get(f.data_field.resolver_key)
                if resolver:
                    select_related.update(resolver.select_related)
                    prefetch_related.update(resolver.prefetch_related)
        # select_related for the relation behind each hidden extra ORM path.
        for path in extra_field_paths:
            if '__' in path:
                select_related.add(path.rsplit('__', 1)[0])

        if select_related:
            queryset = queryset.select_related(*select_related)
        if prefetch_related:
            queryset = queryset.prefetch_related(*prefetch_related)

        ctx = {'user': user}
        results = []
        for instance in queryset:
            row = {}
            for f in fields:
                data_field = f.data_field
                key = data_field.field_path
                if not DataService._field_visible(data_field, user):
                    row[key] = None
                    continue
                if getattr(data_field, 'source_type', DataField.SOURCE_ORM) == DataField.SOURCE_RESOLVER:
                    resolver = REPORTING_RESOLVERS.get(data_field.resolver_key)
                    row[key] = resolver.fn(instance, ctx) if resolver else None
                else:
                    row[key] = DataService._walk_path(instance, data_field.field_path)
            # Hidden extra paths (e.g. a split key) not already displayed.
            for path in extra_field_paths:
                if path not in display_paths:
                    row[path] = DataService._walk_path(instance, path)
            results.append(row)
        return results