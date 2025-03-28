from django.contrib import admin
from .models import (
    Report, ReportCategory, ReportField, ReportFilter, ReportSort,
    DataArea, DataField, DataSource, RelationshipType,
    FieldType, FieldPresentation, FilterType, FilterCondition
)

# Register basic models with simple admin interfaces
admin.site.register(ReportCategory)
admin.site.register(RelationshipType)


# Report admin
class ReportFieldInline(admin.TabularInline):
    model = ReportField
    extra = 1
    ordering = ['position']


class ReportFilterInline(admin.TabularInline):
    model = ReportFilter
    extra = 1
    ordering = ['position']


class ReportSortInline(admin.TabularInline):
    model = ReportSort
    extra = 1
    ordering = ['position']


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'data_area', 'is_private', 'created_at', 'updated_at']
    list_filter = ['is_private', 'data_area', 'owner', 'presentation_type']
    search_fields = ['name', 'description', 'owner__username', 'owner__email']
    readonly_fields = ['created_at', 'updated_at', 'last_run_at', 'uuid']
    fieldsets = [
        ('Basic Information', {
            'fields': ['name', 'description', 'owner', 'category', 'is_private', 'uuid']
        }),
        ('Data Source', {
            'fields': ['data_area', 'population_filter']
        }),
        ('Presentation', {
            'fields': ['presentation_type', 'presentation_options', 'allow_presentation_choice']
        }),
        ('Tracking', {
            'fields': ['created_at', 'updated_at', 'last_run_at']
        }),
    ]
    inlines = [ReportFieldInline, ReportFilterInline, ReportSortInline]
    save_on_top = True


# DataArea admin
class DataFieldInline(admin.TabularInline):
    model = DataField
    extra = 1
    ordering = ['group', 'display_name']


@admin.register(DataArea)
class DataAreaAdmin(admin.ModelAdmin):
    list_display = ['name', 'model_name', 'is_available']
    list_filter = ['is_available']
    search_fields = ['name', 'description', 'model_name']
    inlines = [DataFieldInline]


# DataField admin
@admin.register(DataField)
class DataFieldAdmin(admin.ModelAdmin):
    list_display = ['display_name', 'data_area', 'field_path', 'field_type', 'is_available', 'is_sensitive']
    list_filter = ['data_area', 'field_type', 'is_available', 'is_sensitive', 'group']
    search_fields = ['name', 'display_name', 'field_path', 'description']


# DataSource admin
@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = ['from_area', 'to_area', 'relationship_type', 'is_available']
    list_filter = ['from_area', 'to_area', 'relationship_type', 'is_available']
    search_fields = ['display_name', 'description', 'join_field']


# FieldType admin
class FieldPresentationInline(admin.TabularInline):
    model = FieldPresentation
    extra = 1


@admin.register(FieldType)
class FieldTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'django_field_type', 'is_available', 'can_filter', 'can_sort']
    list_filter = ['is_available', 'can_filter', 'can_sort']
    search_fields = ['name', 'description', 'django_field_type']
    inlines = [FieldPresentationInline]


# FieldPresentation admin
@admin.register(FieldPresentation)
class FieldPresentationAdmin(admin.ModelAdmin):
    list_display = ['name', 'field_type', 'format_string', 'is_available']
    list_filter = ['field_type', 'is_available']
    search_fields = ['name', 'description', 'format_string']


# FilterType admin
class FilterConditionInline(admin.TabularInline):
    model = FilterCondition
    extra = 1


@admin.register(FilterType)
class FilterTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'operator', 'display_label', 'requires_value', 'is_available', 'display_order']
    list_filter = ['requires_value', 'supports_multiple_values', 'is_available']
    search_fields = ['name', 'description', 'operator', 'display_label']
    filter_horizontal = ['applicable_field_types']
    inlines = [FilterConditionInline]


# FilterCondition admin
@admin.register(FilterCondition)
class FilterConditionAdmin(admin.ModelAdmin):
    list_display = ['name', 'field_type', 'filter_type', 'is_dynamic', 'display_order']
    list_filter = ['field_type', 'filter_type', 'is_dynamic']
    search_fields = ['name', 'description', 'value', 'display_label']