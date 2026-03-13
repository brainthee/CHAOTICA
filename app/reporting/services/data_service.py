from django.db.models import Q, F, Value, CharField, Count, Sum, Max, Min, Avg
from django.db.models.functions import Concat
from django.contrib.contenttypes.models import ContentType
from django.apps import apps
from django.core.exceptions import PermissionDenied

from ..models import DataArea, DataField, Report, ReportField, ReportFilter, ReportSort
from ..utils.query_builder import build_query_from_report

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
    def get_report_data(report, user, filter_values=None):
        """
        Execute a report and return the data
        """
        # Check if user has permission to run this report
        if not report.can_view(user):
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
        
        # Apply sorting
        sorts = report.get_sorts()
        if sorts:
            sort_params = []
            for sort in sorts:
                field_path = sort.data_field.field_path
                if sort.direction == 'desc':
                    field_path = f"-{field_path}"
                sort_params.append(field_path)
            
            if sort_params:
                queryset = queryset.order_by(*sort_params)
        
        # Execute the query and return the results
        return DataService._execute_query(queryset, fields)
    
    @staticmethod
    def _apply_permission_filter(queryset, data_area, user):
        """
        Apply permission filtering to the queryset
        This is where you would implement object-level permissions
        """
        model_name = data_area.model_name
        
        # Check if the model has a specific permission filter method
        model_class = queryset.model
        if hasattr(model_class, 'filter_by_user_permissions'):
            return model_class.filter_by_user_permissions(queryset, user)
        
        # Default permission handling based on your application's needs
        # For example, if the model has an 'owner' field:
        if user.is_superuser:
            return queryset
            
        # The following are examples of how you might implement permission filtering
        # Uncomment and modify based on your application's needs
        
        # Example 1: Using guardian's get_objects_for_user
        # from guardian.shortcuts import get_objects_for_user
        # return get_objects_for_user(user, f'{model_name}.view_{model_name}', queryset)
        
        # Example 2: Filter by ownership
        # if hasattr(model_class, 'owner'):
        #     return queryset.filter(owner=user)
            
        # Example 3: Custom permission scheme based on model name
        # if model_name == 'job':
        #     return queryset.filter(Q(unit__in=user.units.all()) | Q(created_by=user))
        # elif model_name == 'project':
        #     return queryset.filter(team__members=user)
        
        return queryset
    
    @staticmethod
    def _execute_query(queryset, fields):
        """
        Execute the query and format the results.
        Supports aggregation: if any field has an aggregation_function set,
        non-aggregated fields become GROUP BY columns via .values(),
        and aggregated fields use .annotate().
        """
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

            # Reorder result keys to match the original field order
            ordered_results = []
            for row in results:
                ordered_row = {}
                for field in fields:
                    field_path = field.data_field.field_path
                    agg_func = getattr(field, 'aggregation_function', '')
                    if agg_func and agg_func in AGGREGATION_MAP:
                        alias = f"{agg_func}_{field_path}".replace('__', '_')
                        ordered_row[alias] = row.get(alias)
                    else:
                        ordered_row[field_path] = row.get(field_path)
                ordered_results.append(ordered_row)
            return ordered_results
        else:
            # No aggregation — original behaviour
            field_paths = [field.data_field.field_path for field in fields]
            results = queryset.values(*field_paths)
            return list(results)