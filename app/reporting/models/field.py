from django.db import models

class FieldType(models.Model):
    """Defines different types of fields (text, number, date, etc.)"""
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True, null=True)
    
    # Django internal type mapping
    django_field_type = models.CharField(max_length=50, help_text="Corresponding Django field type")
    
    # Default presentation format
    default_format = models.CharField(max_length=100, blank=True, null=True)
    
    # Whether this field type is available for reporting
    is_available = models.BooleanField(default=True)
    
    # Whether this field type can be used for filtering
    can_filter = models.BooleanField(default=True)
    
    # Whether this field type can be used for sorting
    can_sort = models.BooleanField(default=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']


class FieldPresentation(models.Model):
    """Defines how a field can be presented in a report"""
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True, null=True)
    
    # Field type this presentation applies to
    field_type = models.ForeignKey(FieldType, on_delete=models.CASCADE, related_name='presentations')
    
    # Format string
    format_string = models.CharField(max_length=255, blank=True, null=True)
    
    # CSS class for HTML presentation
    css_class = models.CharField(max_length=50, blank=True, null=True)
    
    # Whether this presentation is available
    is_available = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.name} ({self.field_type.name})"
    
    class Meta:
        ordering = ['field_type', 'name']
        verbose_name = 'Field Presentation'
        verbose_name_plural = 'Field Presentations'