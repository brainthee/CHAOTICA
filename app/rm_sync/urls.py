from django.urls import path, include, re_path
from . import views


urlpatterns = [
    path("settings", views.rm_settings, name="rm_settings"),
    path("update", views.rm_update_record, name="rm_update_record"),
    path("unit-map/<int:pk>", views.rm_update_unit_map, name="rm_update_unit_map"),
    path("import-users", views.rm_import_users, name="rm_import_users"),
    path("apply-maps", views.rm_apply_maps, name="rm_apply_maps"),
    path("import-clients", views.rm_import_clients, name="rm_import_clients"),
    path("run", views.rm_run_sync, name="rm_run_sync"),
    path("pull-preview", views.rm_pull_preview, name="rm_pull_preview"),
    path("clear", views.rm_clear_projects, name="rm_clear_projects"),
]
