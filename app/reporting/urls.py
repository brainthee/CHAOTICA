from django.urls import path
from .views import wizard, reports, ajax

app_name = 'reporting'

urlpatterns = [
    # Main pages
    path('', reports.index, name='index'),
    path('reports/', reports.ReportListView.as_view(), name='report_list'),
    path('reports/<uuid:uuid>/', reports.ReportDetailView.as_view(), name='report_detail'),
    path('reports/<uuid:uuid>/run/', reports.run_report, name='run_report'),
    path('reports/<uuid:uuid>/delete/', reports.ReportDeleteView.as_view(), name='report_delete'),
    path('reports/<uuid:uuid>/favorite/', reports.toggle_favorite, name='toggle_favorite'),
    path('categories/create/', reports.create_category, name='create_category'),
    
    # Wizard
    path('wizard/', wizard.wizard_start, name='wizard_start'),
    path('wizard/edit/<uuid:report_uuid>/', wizard.wizard_start, name='wizard_edit'),
    path('wizard/data-area/', wizard.wizard_select_data_area, name='wizard_select_data_area'),
    path('wizard/fields/', wizard.wizard_select_fields, name='wizard_select_fields'),
    path('wizard/filters/', wizard.wizard_define_filters, name='wizard_define_filters'),
    path('wizard/sort/', wizard.wizard_define_sort, name='wizard_define_sort'),
    path('wizard/presentation/', wizard.wizard_define_presentation, name='wizard_define_presentation'),
    path('wizard/preview/', wizard.wizard_preview, name='wizard_preview'),
    path('wizard/cancel/', wizard.wizard_cancel, name='wizard_cancel'),
    
    # AJAX endpoints for wizard
    path('wizard/field-customize/', wizard.wizard_field_customize, name='wizard_field_customize'),
    path('wizard/field-reorder/', wizard.wizard_field_reorder, name='wizard_field_reorder'),
    
    # AJAX endpoints
    path('ajax/data-area-fields/', ajax.get_data_area_fields, name='ajax_data_area_fields'),
    path('ajax/field-filter-types/', ajax.get_field_filter_types, name='ajax_field_filter_types'),
    path('ajax/filter-widget/', ajax.get_filter_widget, name='ajax_filter_widget'),
    path('ajax/population-filters/', ajax.get_population_filters, name='ajax_population_filters'),
    path('ajax/related-data-areas/', ajax.get_related_data_areas, name='ajax_related_data_areas'),
    path('ajax/reports/<uuid:uuid>/update-field/', ajax.update_report_field, name='ajax_update_report_field'),
    path('ajax/reports/<uuid:uuid>/reorder-fields/', ajax.reorder_report_fields, name='ajax_reorder_report_fields'),
    path('ajax/reports/<uuid:uuid>/preview-data/', ajax.preview_report_data, name='ajax_preview_report_data'),
]