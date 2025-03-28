from django.db import models

class FilterType(models.Model):
    """Defines different types of filters (equals, contains, greater than, etc.)"""
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True, null=True)
    
    # Internal operator for query building
    operator = models.CharField(max_length=50, help_text="Django query operator (e.g., 'exact', 'contains')")
    
    # Display label for user interface
    display_label = models.CharField(max_length=50)
    
    # Field types this filter can be applied to
    applicable_field_types = models.ManyToManyField('FieldType', related_name='filter_types')
    
    # Whether this filter requires a value
    requires_value = models.BooleanField(default=True)
    
    # Whether this filter can accept multiple values
    supports_multiple_values = models.BooleanField(default=False)
    
    # Whether this filter is available
    is_available = models.BooleanField(default=True)
    
    # Order for display in UI
    display_order = models.PositiveIntegerField(default=0)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['display_order', 'name']


class FilterCondition(models.Model):
    """Represents predefined filter conditions"""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    
    # Field type this condition applies to
    field_type = models.ForeignKey('FieldType', on_delete=models.CASCADE, related_name='filter_conditions')
    
    # Filter type
    filter_type = models.ForeignKey(FilterType, on_delete=models.CASCADE)
    
    # Predefined value or expression
    value = models.TextField(blank=True, null=True)
    
    # Whether this is a dynamic value (e.g., "today", "current user")
    is_dynamic = models.BooleanField(default=False)
    
    # Display label for user interface
    display_label = models.CharField(max_length=100)
    
    # Order for display in UI
    display_order = models.PositiveIntegerField(default=0)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['display_order', 'name']