"""
Main views module imports views from submodules for backward compatibility
and easier imports.
"""

from .views.list import ReportListView
from .views.detail import ReportDetailView, ReportRunView
from .views.wizard import (
    ReportWizardView,
    report_wizard_step1,
    report_wizard_step2,
    report_wizard_step3,
    report_wizard_step4,
    report_wizard_step5,
    report_wizard_step6,
)
from .views.manage import (
    ReportUpdateView,
    ReportDeleteView,
    ReportScheduleCreateView,
    ReportScheduleUpdateView,
    ReportScheduleDeleteView,
)
from .views.api import (
    api_field_data,
    api_report_preview,
)

# Expose all views for easier imports
__all__ = [
    'ReportListView',
    'ReportDetailView',
    'ReportRunView',
    'ReportWizardView',
    'report_wizard_step1',
    'report_wizard_step2',
    'report_wizard_step3',
    'report_wizard_step4',
    'report_wizard_step5',
    'report_wizard_step6',
    'ReportUpdateView',
    'ReportDeleteView',
    'ReportScheduleCreateView',
    'ReportScheduleUpdateView',
    'ReportScheduleDeleteView',
    'api_field_data',
    'api_report_preview',
]