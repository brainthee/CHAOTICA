from django.db import models
from django.contrib.contenttypes.models import ContentType
import json

class RelationshipType(models.Model):
    """Defines relationship types between data areas (one-to-many, many-to-many)"""
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return self.name


class DataArea(models.Model):
    """Represents a major data area like Users, Jobs, Phases, etc."""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    
    # Link to Django model (content type)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    model_name = models.CharField(max_length=100)
    
    # Population filters available (stored as JSON)
    population_options = models.JSONField(default=dict, blank=True, 
                                         help_text="JSON definition of population filter options")
    
    # Relationships to other data areas
    related_areas = models.ManyToManyField(
        'self', through='DataSource', 
        symmetrical=False, 
        related_name='parent_areas'
    )
    
    # Default sort field
    default_sort_field = models.CharField(max_length=100, blank=True, null=True)
    
    # Whether this area should be available in report builder
    is_available = models.BooleanField(default=True)
    icon_class = models.CharField(max_length=50, blank=True, null=True, help_text="CSS class for icon representation")
    
    def __str__(self):
        return self.name
    
    def get_fields(self):
        """Get all available fields for this data area"""
        return self.fields.filter(is_available=True).order_by('group', 'name')
    
    def get_available_populations(self):
        """Returns a dictionary of available population filters"""
        if not self.population_options:
            return {}
        return self.population_options
    
    def get_related_areas(self):
        """Get all related data areas that can be included in reports"""
        return DataArea.objects.filter(parent_sources__from_area=self, is_available=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = 'Data Area'
        verbose_name_plural = 'Data Areas'


class DataSource(models.Model):
    """Represents a relationship between two data areas"""
    from_area = models.ForeignKey(DataArea, on_delete=models.CASCADE, related_name='child_sources')
    to_area = models.ForeignKey(DataArea, on_delete=models.CASCADE, related_name='parent_sources')
    relationship_type = models.ForeignKey(RelationshipType, on_delete=models.CASCADE)
    
    # Technical details for joining
    join_field = models.CharField(max_length=100)
    reverse_join_field = models.CharField(max_length=100, blank=True, null=True)
    
    # Display information
    display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    
    # Whether this relationship should be available
    is_available = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.from_area} → {self.to_area} ({self.relationship_type})"
    
    class Meta:
        unique_together = ('from_area', 'to_area', 'join_field')
        verbose_name = 'Data Source'
        verbose_name_plural = 'Data Sources'


class DataField(models.Model):
    """Represents an available field in a data area"""
    data_area = models.ForeignKey(DataArea, on_delete=models.CASCADE, related_name='fields')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    
    # Field technical details
    field_path = models.CharField(max_length=255, help_text="Path to the field in the model")
    field_type = models.ForeignKey('FieldType', on_delete=models.CASCADE)
    
    # Display information
    display_name = models.CharField(max_length=100)
    group = models.CharField(max_length=100, blank=True, null=True, help_text="Group name for organizing fields")
    
    # Whether this field can be used in reports
    is_available = models.BooleanField(default=True)
    is_sensitive = models.BooleanField(default=False, help_text="Whether this field contains sensitive information")
    requires_permission = models.CharField(max_length=100, blank=True, null=True, 
                                          help_text="Permission codename required to view this field")
    
    # Default presentation
    default_presentation = models.ForeignKey('FieldPresentation', on_delete=models.SET_NULL, null=True, blank=True)
    
    def __str__(self):
        return f"{self.display_name} ({self.data_area.name})"
    
    def get_available_filter_types(self):
        """Get filter types available for this field based on its type"""
        return self.field_type.filter_types.filter(is_available=True)
    
    class Meta:
        ordering = ['group', 'display_name']
        unique_together = ('data_area', 'field_path')