from django.urls import path, include
from . import views

app_name = 'reporting'

urlpatterns = [
    # Report listing and management
    path('', views.ReportListView.as_view(), name='report_list'),
    path('<int:pk>/', views.ReportDetailView.as_view(), name='report_detail'),
    path('<int:pk>/edit/', views.ReportUpdateView.as_view(), name='report_edit'),
    path('<int:pk>/delete/', views.ReportDeleteView.as_view(), name='report_delete'),
    
    # Report wizard
    path('wizard/', views.ReportWizardView.as_view(), name='report_wizard'),
    path('wizard/step1/', views.report_wizard_step1, name='report_wizard_step1'),
    path('wizard/step2/', views.report_wizard_step2, name='report_wizard_step2'),
    path('wizard/step3/', views.report_wizard_step3, name='report_wizard_step3'),
    path('wizard/step4/', views.report_wizard_step4, name='report_wizard_step4'),
    path('wizard/step5/', views.report_wizard_step5, name='report_wizard_step5'),
    path('wizard/step6/', views.report_wizard_step6, name='report_wizard_step6'),
    
    # Running reports
    path('<int:pk>/run/', views.ReportRunView.as_view(), name='report_run'),
    path('<int:pk>/preview/', views.api_report_preview, name='report_preview'),
    
    # Scheduling
    path('<int:report_id>/schedule/add/', views.ReportScheduleCreateView.as_view(), name='schedule_create'),
    path('schedule/<int:pk>/edit/', views.ReportScheduleUpdateView.as_view(), name='schedule_edit'),
    path('schedule/<int:pk>/delete/', views.ReportScheduleDeleteView.as_view(), name='schedule_delete'),
    
    # API endpoints
    path('api/fields/<str:data_area>/', views.api_field_data, name='api_field_data'),
]