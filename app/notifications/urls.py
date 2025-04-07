from django.urls import path
from . import views

urlpatterns = [
    # Notifications
    # Notification API endpoints
    path('api/', views.notifications_api, name='notifications_api'),
    path('api/mark-all-read/', views.mark_all_read, name='mark_all_read'),
    path('api/subscription/delete/', views.remove_notification_subscription, name='remove_notification_subscription'),
    path('api/subscription/update/', views.update_subscription_settings, name='update_subscription_settings'),
    path('api/follow/', views.follow_entity, name='follow_entity'),
    path('api/unfollow/', views.unfollow_entity, name='unfollow_entity'),
    path('api/subscription-status/', views.notification_subscription_status, name='notification_subscription_status'),
    path('api/user-subscriptions/', views.get_user_subscriptions, name='get_user_subscriptions'),
    path('api/unread-count/', views.get_unread_count, name='get_unread_count'),
    path('api/types/', views.get_notification_types, name='get_notification_types'),
    path('settings/', views.notification_settings, name='notification_settings'),
]
