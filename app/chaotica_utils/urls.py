from django.urls import path, include, re_path
from . import views


urlpatterns = [
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
    path("signup/<str:invite_id>", views.signup, name="signup"),
    path("signup/", views.signup, name="signup"),

    # Notifications
    path("notifications/", views.notifications_feed, name="notifications_feed"),
    path(
        "notifications/<int:pk>/mark_read",
        views.notification_mark_read,
        name="notification_mark_read",
    ),
    path(
        "notifications/mark_all_read",
        views.notifications_mark_read,
        name="notifications_mark_read",
    ),

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
    path("activity/", views.NoteListView.as_view(), name="view_activity"),

    # Own profile bits
    path("profile/", views.view_own_profile, name="view_own_profile"),
    path("profile/theme", views.update_own_theme, name="update_own_theme"),
    path("profile/update", views.update_own_profile, name="update_own_profile"),
    path("profile/update/skills", views.update_own_skills, name="update_own_skills"),
    path("profile/update/certs", views.update_own_certs, name="update_own_certs"),
    path("profile/onboarding/", views.view_own_onboarding, name="view_own_onboarding"),
    path("profile/onboarding/renew/<int:pk>", views.renew_own_onboarding, name="renew_own_onboarding"),
    path("profile/leave/", views.view_own_leave, name="view_own_leave"),
    path("profile/leave/request", views.request_own_leave, name="request_own_leave"),
    path(
        "profile/leave/<int:pk>/cancel", views.cancel_own_leave, name="cancel_own_leave"
    ),
    # Other user profile bits
    path("profile/<str:email>", views.UserDetailView.as_view(), name="user_profile"),
    path(
        "profile/<str:email>/update/",
        views.UserUpdateView.as_view(),
        name="user_update",
    ),
    path(
        "profile/<str:email>/assign_role/",
        views.user_assign_global_role,
        name="user_assign_global_role",
    ),
    path(
        "profile/<str:email>/delete/",
        views.UserDeleteView.as_view(),
        name="user_delete",
    ),
    path("profile/<str:email>/manage/", views.user_manage, name="user_manage"),
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
