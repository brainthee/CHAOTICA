from django.urls import path, include, re_path
from . import views
from django.contrib.auth import views as auth_views


urlpatterns = [
    path('auth/login/', views.LoginView.as_view(redirect_authenticated_user=True), name='login'),
    path("auth/", include("django.contrib.auth.urls")),
    path("maintenance/", views.maintenance, name="maintenance"),
    re_path(r"^impersonate/", include("impersonate.urls")),
    path("quote", views.get_quote, name="get_quote"),

    # Autocomplete/search
    path(
        "autocomplete/users", views.UserAutocomplete.as_view(), name="user-autocomplete"
    ),
    path("search", views.site_search, name="search"),
    
    # User CRUD
    path("users/", views.UserListView.as_view(), name="user_list"),
    path("users/map", views.map_view, name="map_view"),
    path("users/invite", views.user_invite, name="user_invite"),
    path("sessions/", views.SessionListView.as_view(), name="session_list"),
    path("signup/<str:invite_id>", views.signup, name="signup"),
    path("signup/", views.signup, name="signup"),

    # Annual Leave
    path("ops/leave/", views.manage_leave, name="manage_leave"),
    path(
        "ops/leave/<int:pk>/manage",
        views.manage_leave_auth_request,
        name="manage_leave_auth_request",
    ),
    # Holidays
    path("ops/holidays/", views.HolidayListView.as_view(), name="holiday_list"),
    path("ops/holidays/create/", views.holiday_create, name="holiday_create"),
    path("ops/holidays/import_lib/", views.holiday_import_lib, name="holiday_import_lib"),
    path(
        "ops/holidays/<str:pk>/update/",
        views.holiday_edit,
        name="holiday_update",
    ),
    path(
        "ops/holidays/<str:pk>/delete/",
        views.holiday_delete,
        name="holiday_delete",
    ),

    # Settings
    path("settings/", views.app_settings, name="app_settings"),
    path("settings/import", views.settings_import_data, name="settings_import_data"),
    path("settings/export", views.settings_export_data, name="settings_export_data"),
    path("settings/csv_template/users", views.csv_template_users, name="csv_template_users"),

    path('settings/backup/db/download', views.download_db_backup, name='download_db_backup'),
    path('settings/backup/media/download', views.download_media_backup, name='download_media_backup'),
    path('settings/backup/db/restore', views.restore_db_backup, name='restore_db_backup'),
    path('settings/backup/media/restore', views.restore_media_backup, name='restore_media_backup'),

    path("activity/", views.NoteListView.as_view(), name="view_activity"),

    # Own profile bits
    path("profile/", views.view_own_profile, name="view_own_profile"), # redirect to public profile
    path("profile/update", views.update_own_profile, name="update_own_profile"), # redirect to edit profile

    path("profile/theme", views.update_own_theme, name="update_own_theme"),    
    path("profile/leave/", views.view_own_leave, name="view_own_leave"),
    path("profile/leave/request", views.request_own_leave, name="request_own_leave"),
    path(
        "profile/leave/<int:pk>/cancel", views.cancel_own_leave, name="cancel_own_leave"
    ),
    # Other user profile bits
    path("profile/<str:email>", views.UserDetailView.as_view(), name="user_profile"),
    path(
        "profile/<str:email>/assign_role/",
        views.user_assign_global_role,
        name="user_assign_global_role",
    ),
    path("profile/<str:email>/update/", views.update_profile, name="update_profile"),
    path("profile/<str:email>/update/skills", views.update_skills, name="update_skills"),
    path("profile/<str:email>/update/certs", views.update_certs, name="update_certs"),
    path("profile/<str:email>/onboarding/", views.view_onboarding, name="view_onboarding"),
    path("profile/<str:email>/onboarding/renew/<int:pk>", views.renew_onboarding, name="renew_onboarding"),
    path("profile/<str:email>/schedule/timeslots/", views.user_schedule_timeslots, name="user_schedule_timeslots"),
    path("profile/<str:email>/schedule/holidays/", views.user_schedule_holidays, name="user_schedule_holidays"),
    path("profile/<str:email>/manage/merge", views.user_merge, name="user_merge"),
    path(
        "profile/<str:email>/manage/status/<str:state>/",
        views.user_manage_status,
        name="user_manage_status",
    ),
    # Admin tasks/triggers
        
    path(
        "admin_tasks/trigger_error",
        views.admin_trigger_error,
        name="admin_trigger_error",
    ),    
    path(
        "admin_tasks/send_test_notification",
        views.admin_send_test_notification,
        name="admin_send_test_notification",
    ),

    path(
        "admin_tasks/update_phase_dates",
        views.admin_task_update_phase_dates,
        name="admin_task_update_phase_dates",
    ),
    path(
        "admin_tasks/sync_global_permissions",
        views.admin_task_sync_global_permissions,
        name="admin_task_sync_global_permissions",
    ),
    path(
        "admin_tasks/sync_role_permissions_to_default",
        views.admin_task_sync_role_permissions_to_default,
        name="admin_task_sync_role_permissions_to_default",
    ),
    path(
        "admin_tasks/sync_role_permissions",
        views.admin_task_sync_role_permissions,
        name="admin_task_sync_role_permissions",
    ),
]
