from django.urls import path, include, re_path
from . import views


urlpatterns = [
    path("settings", views.rm_settings, name="rm_settings"),
    path("update", views.rm_update_record, name="rm_update_record"),
    path("run", views.rm_run_sync, name="rm_run_sync"),
    path("clear", views.rm_clear_projects, name="rm_clear_projects"),
]