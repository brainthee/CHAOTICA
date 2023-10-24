from django.urls import path, include, re_path 
from . import views
from django.contrib import admin


urlpatterns = [
    path('signup/<str:invite_id>', views.signup, name='signup'),
    path('signup/', views.signup, name='signup'),
    path("auth/", include("django.contrib.auth.urls")),
    path("admin/", admin.site.urls),
    path('debug/sentry', views.trigger_error, name="trigger_error"),
    path('debug/test_notification', views.test_notification, name="test_notification"),
    path('maintenance/', views.maintenance, name='maintenance'),
    re_path(r'^impersonate/', include('impersonate.urls')),
    path('quote', views.get_quote, name='get_quote'),
    path('autocomplete/users', views.UserAutocomplete.as_view(), name='user-autocomplete'),
    # path('autocomplete/job', views.JobAutocomplete.as_view(), name='job-autocomplete'),
    path('search', views.site_search, name='search'),

    # User CRUD
    path('users/', views.UserListView.as_view(), name='user_list'),
    path('users/invite', views.user_invite, name='user_invite'),
    path('notifications/', views.notifications_feed, name='notifications_feed'),
    path('notifications/<int:pk>/mark_read', views.notification_mark_read, name='notification_mark_read'),
    path('notifications/mark_all_read', views.notifications_mark_read, name='notifications_mark_read'),
    path('leave/', views.view_own_leave, name='view_own_leave'),
    path('leave/request', views.request_leave, name='request_leave'),
    path('leave/<int:pk>/cancel', views.cancel_own_leave, name='cancel_own_leave'),
    path('ops/leave/', views.manage_leave, name='manage_leave'),
    path('ops/leave/<int:pk>/manage', views.manage_leave_auth_request, name='manage_leave_auth_request'),
    path('settings/', views.app_settings, name='app_settings'),
    path('profile/', views.view_own_profile, name='view_own_profile'),
    path('profile/theme', views.update_own_theme, name='update_own_theme'),
    path('profile/update', views.update_own_profile, name='update_own_profile'),
    path('profile/update/skills', views.update_own_skills, name='update_own_skills'),    
    path('profile/update/certs', views.update_own_certs, name='update_own_certs'),    
    path('profile/<str:username>', views.UserDetailView.as_view(), name='user_profile'),
    path('profile/<str:username>/update/', views.UserUpdateView.as_view(), name='user_update'),
    path('profile/<str:username>/assign_role/', views.user_assign_global_role, name='user_assign_global_role'),
    path('profile/<str:username>/delete/', views.UserDeleteView.as_view(), name='user_delete'),

    path('tasks/update_holidays', views.update_holidays, name='update_holidays'),
]