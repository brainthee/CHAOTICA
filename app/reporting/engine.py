from django.db.models import Q, Sum, Count, Avg, Min, Max, F, Value, CharField, FloatField
from django.db.models.functions import Concat, Cast
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
import logging
import re

from chaotica_utils.models import User, LeaveRequest
from jobtracker.models import (
    Job, Phase, TimeSlot, Project, Client, Team, Skill, 
    OrganisationalUnit, OrganisationalUnitMember
)
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)

class ReportEngine:
    """Core engine for executing report definitions"""
    
    def __init__(self, report_definition, user):
        self.report = report_definition
        self.user = user
        self.model_map = {
            'user': User,
            'job': Job,
            'phase': Phase,
            'timeslot': TimeSlot,
            'project': Project,
            'client': Client,
            'team': Team,
            'skill': Skill,
            'organisational_unit': OrganisationalUnit,
            'leave_request': LeaveRequest,
        }
        
        # Mapping of custom aggregation functions
        self.aggregation_map = {
            'sum': Sum,
            'count': Count,
            'avg': Avg,
            'min': Min,
            'max': Max,
        }
    
    def execute(self, params=None):
        """Execute the report and return the results"""
        try:
            # Get the base queryset for the data area
            queryset = self._get_base_queryset()
            
            # Apply population filters
            queryset = self._apply_population_filter(queryset)
            
            # Apply user-defined filters (including any runtime params)
            queryset = self._apply_filters(queryset, params)
            
            # Apply field selection and annotations
            queryset = self._select_fields(queryset)
            
            # Apply sorting
            queryset = self._apply_sorting(queryset)
            
            # Execute the query and return results
            return self._execute_query(queryset)
            
        except Exception as e:
            logger.error(f"Error executing report {self.report.id}: {str(e)}")
            raise
    
    def _get_base_queryset(self):
        """Get the base queryset for the report's data area"""
        data_area = self.report.data_area
        
        if data_area not in self.model_map:
            raise ImproperlyConfigured(f"Unknown data area: {data_area}")
        
        model = self.model_map[data_area]
        
        # Start with basic queryset - apply permissions as needed
        if data_area == 'job':
            # Example: Only jobs the user can see
            from guardian.shortcuts import get_objects_for_user
            units = get_objects_for_user(
                self.user, "jobtracker.can_view_jobs", OrganisationalUnit
            )
            return Job.objects.filter(unit__in=units)
        elif data_area == 'user':
            return User.objects.filter(is_active=True)
        else:
            # Default case
            return model.objects.all()
    
    def _apply_population_filter(self, queryset):
        """Apply population-level filters to the queryset"""
        data_area = self.report.data_area
        population_filter = self.report.population_filter
        
        if not population_filter:
            return queryset
            
        if data_area == 'user':
            # Example population filters for users
            if population_filter.get('type') == 'active_only':
                queryset = queryset.filter(is_active=True)
            elif population_filter.get('type') == 'with_manager':
                queryset = queryset.filter(manager__isnull=False)
                
        elif data_area == 'job':
            # Example population filters for jobs
            if population_filter.get('type') == 'active_only':
                queryset = queryset.exclude(status__in=[4, 5])  # Example: Exclude deleted/archived
            elif population_filter.get('type') == 'current_year':
                current_year = timezone.now().year
                queryset = queryset.filter(
                    created_at__year=current_year
                )
                
        # More data areas can be added as needed
        
        return queryset
    
    def _apply_filters(self, queryset, runtime_params=None):
        """Apply user-defined filters to the queryset"""
        filters = self.report.filter_conditions
        
        if not filters:
            return queryset
            
        # Combine filters with AND/OR logic
        combined_filter = Q()
        
        for filter_group in filters:
            group_filter = Q()
            group_op = filter_group.get('operator', 'AND')
            
            for condition in filter_group.get('conditions', []):
                field = condition.get('field')
                operator = condition.get('operator')
                value = condition.get('value')
                prompt_id = condition.get('prompt_id')
                
                # Handle runtime parameters if this is a prompted filter
                if prompt_id and runtime_params and prompt_id in runtime_params:
                    value = runtime_params[prompt_id]
                
                # Skip if any required part is missing
                if not all([field, operator]):
                    continue
                
                # Convert the operator to Django's ORM syntax
                field_lookup = self._get_field_lookup(field, operator)
                
                # Handle special cases for date fields
                if operator in ['today', 'yesterday', 'this_week', 'this_month', 'this_year']:
                    value = self._get_date_value(operator)
                
                # Build the filter expression
                if operator == 'is_null':
                    filter_expr = {field_lookup: True}
                elif operator == 'is_not_null':
                    filter_expr = {field_lookup: False}
                else:
                    filter_expr = {field_lookup: value}
                
                # Add to the group filter with the appropriate logic
                condition_q = Q(**filter_expr)
                if group_op.upper() == 'AND':
                    group_filter &= condition_q
                else:  # OR
                    group_filter |= condition_q
            
            # Add the group to the combined filter
            combined_filter &= group_filter
        
        return queryset.filter(combined_filter)
    
    def _get_field_lookup(self, field, operator):
        """Convert a filter operator to a Django field lookup"""
        operator_map = {
            'equals': field,
            'not_equals': f"{field}__exact",
            'contains': f"{field}__icontains",
            'not_contains': f"{field}__icontains",
            'starts_with': f"{field}__istartswith",
            'ends_with': f"{field}__iendswith",
            'greater_than': f"{field}__gt",
            'less_than': f"{field}__lt",
            'greater_than_or_equal': f"{field}__gte",
            'less_than_or_equal': f"{field}__lte",
            'in': f"{field}__in",
            'not_in': f"{field}__in",
            'is_null': f"{field}__isnull",
            'is_not_null': f"{field}__isnull",
            'date_equals': f"{field}__date",
            'date_greater_than': f"{field}__date__gt",
            'date_less_than': f"{field}__date__lt",
            'year_equals': f"{field}__year",
            'month_equals': f"{field}__month",
            'day_equals': f"{field}__day",
        }
        
        if operator in operator_map:
            return operator_map[operator]
        
        # Default case
        return field
    
    def _get_date_value(self, operator):
        """Get date values for special date operators"""
        today = date.today()
        
        if operator == 'today':
            return today
        elif operator == 'yesterday':
            return today - timedelta(days=1)
        elif operator == 'this_week':
            start_of_week = today - timedelta(days=today.weekday())
            return (start_of_week, start_of_week + timedelta(days=6))
        elif operator == 'this_month':
            return (date(today.year, today.month, 1), 
                    date(today.year, today.month + 1, 1) - timedelta(days=1))
        elif operator == 'this_year':
            return (date(today.year, 1, 1), date(today.year, 12, 31))
        
        return None
    
    def _select_fields(self, queryset):
        """Select and annotate fields for the report"""
        data_area = self.report.data_area
        fields = self.report.selected_fields
        
        if not fields:
            return queryset
        
        # Track which fields we need to select vs annotate
        select_fields = []
        annotations = {}
        
        for field_def in fields:
            field_type = field_def.get('type', 'direct')
            field_name = field_def.get('name')
            display_name = field_def.get('display_name', field_name)
            
            if field_type == 'direct':
                # Direct field from the model
                select_fields.append(field_name)
                
            elif field_type == 'related':
                # Related field (e.g. job__client__name)
                select_fields.append(field_name)
                
            elif field_type == 'concat':
                # Concatenation of multiple fields
                source_fields = field_def.get('source_fields', [])
                separator = field_def.get('separator', ' ')
                
                concat_parts = []
                for source in source_fields:
                    concat_parts.append(F(source))
                    concat_parts.append(Value(separator))
                
                # Remove the last separator
                if concat_parts:
                    concat_parts.pop()
                
                annotations[display_name] = Concat(
                    *concat_parts,
                    output_field=CharField()
                )
                
            elif field_type == 'aggregation':
                # Aggregation (e.g. count of related records)
                agg_type = field_def.get('aggregation', 'count')
                related_field = field_def.get('related_field')
                distinct = field_def.get('distinct', False)
                
                if agg_type in self.aggregation_map:
                    agg_func = self.aggregation_map[agg_type]
                    
                    # Default to counting the ID if no specific field
                    if not related_field and agg_type == 'count':
                        related_field = 'id'
                    
                    annotations[display_name] = agg_func(
                        related_field, 
                        distinct=distinct
                    )
                
            elif field_type == 'calculation':
                # Mathematical calculation on fields
                formula = field_def.get('formula')
                if formula:
                    # Simple implementation for basic arithmetic
                    # For complex calculations, you'd need a formula parser
                    annotations[display_name] = self._parse_formula(formula)
                
            elif field_type == 'custom':
                # Custom expressions that don't fit other categories
                # Would need specific implementations for each use case
                pass
        
        # Apply annotations first
        if annotations:
            queryset = queryset.annotate(**annotations)
        
        # Then apply field selection if specified
        if select_fields:
            # Add all annotation fields to the select list
            select_fields.extend(annotations.keys())
            queryset = queryset.values(*select_fields)
        
        return queryset
    
    def _parse_formula(self, formula):
        """Parse a simple formula string into Django expressions"""
        # This is a basic implementation - for complex formulas, use a proper parser
        # Supports basic arithmetic on F objects: F('field1') + F('field2') * 2
        
        # Replace field references with F expressions
        pattern = r'([a-zA-Z_][a-zA-Z0-9_]*)'
        
        def replace_with_f(match):
            field_name = match.group(1)
            # Skip Python keywords and numeric values
            if field_name in ('and', 'or', 'not', 'in', 'True', 'False', 'None') or field_name.isdigit():
                return field_name
            return f"F('{field_name}')"
        
        formula_with_f = re.sub(pattern, replace_with_f, formula)
        
        # WARNING: eval is used here for simplicity but is generally unsafe
        # A proper implementation would use a safe formula parser
        try:
            from django.db.models import F
            return eval(formula_with_f, {'F': F})
        except Exception as e:
            logger.error(f"Error parsing formula {formula}: {e}")
            return Value(0, output_field=FloatField())
    
    def _apply_sorting(self, queryset):
        """Apply sorting to the queryset"""
        sort_fields = self.report.sort_order
        
        if not sort_fields:
            return queryset
        
        ordering = []
        for sort in sort_fields:
            field = sort.get('field')
            direction = sort.get('direction', 'asc')
            
            if field:
                if direction.lower() == 'desc':
                    ordering.append(f"-{field}")
                else:
                    ordering.append(field)
        
        if ordering:
            return queryset.order_by(*ordering)
        
        return queryset
    
    def _execute_query(self, queryset):
        """Execute the final query and return results"""
        # For large datasets, we might want to implement pagination
        # or streaming to avoid memory issues
        
        try:
            # Execute the query
            results = list(queryset)
            
            # Add any metadata needed for reporting
            metadata = {
                'count': len(results),
                'generated_at': timezone.now(),
                'generated_by': f"{self.user.first_name} {self.user.last_name}",
                'report_name': self.report.name,
            }
            
            return {
                'data': results,
                'metadata': metadata
            }
            
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            raise