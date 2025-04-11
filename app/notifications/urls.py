from django.urls import path
from .views import notifications, subscription_rules

urlpatterns = [
    # Notifications
    # Notification API endpoints
    path('api/', notifications.notifications_api, name='notifications_api'),
    path('api/mark-all-read/', notifications.mark_all_read, name='mark_all_read'),
    path('api/subscription/delete/', notifications.remove_notification_subscription, name='remove_notification_subscription'),
    path('api/subscription/update/', notifications.update_subscription_settings, name='update_subscription_settings'),
    path('api/follow/', notifications.follow_entity, name='follow_entity'),
    path('api/unfollow/', notifications.unfollow_entity, name='unfollow_entity'),
    path('api/subscription-status/', notifications.notification_subscription_status, name='notification_subscription_status'),
    path('api/user-subscriptions/', notifications.get_user_subscriptions, name='get_user_subscriptions'),
    path('api/unread-count/', notifications.get_unread_count, name='get_unread_count'),
    path('api/types/', notifications.get_notification_types, name='get_notification_types'),
    path('settings/', notifications.notification_settings, name='notification_settings'),
    
    # Subscription Rules
    path('rules/', subscription_rules.notification_rules, name='notification_rules'),
    path('rules/create/', subscription_rules.notification_rule_create, name='notification_rule_create'),
    path('rules/<int:rule_id>/', subscription_rules.notification_rule_detail, name='notification_rule_detail'),
    path('rules/<int:rule_id>/edit/', subscription_rules.notification_rule_edit, name='notification_rule_edit'),
    path('rules/<int:rule_id>/delete/', subscription_rules.notification_rule_delete, name='notification_rule_delete'),
    path('rules/<int:rule_id>/toggle/', subscription_rules.notification_rule_toggle, name='notification_rule_toggle'),
    
    # Rule Criteria Management
    path('rules/<int:rule_id>/add-criteria/', subscription_rules.notification_rule_add_criteria, name='notification_rule_add_criteria'),
    path('rules/<int:rule_id>/add-global-criteria/', subscription_rules.notification_rule_add_global_criteria, name='notification_rule_add_global_criteria'),
    path('rules/<int:rule_id>/add-org-criteria/', subscription_rules.notification_rule_add_org_criteria, name='notification_rule_add_org_criteria'),
    path('rules/<int:rule_id>/add-job-criteria/', subscription_rules.notification_rule_add_job_criteria, name='notification_rule_add_job_criteria'),
    path('rules/<int:rule_id>/add-phase-criteria/', subscription_rules.notification_rule_add_phase_criteria, name='notification_rule_add_phase_criteria'),    
    path('rules/<int:rule_id>/add-dynamic-criteria/', subscription_rules.notification_rule_add_dynamic_criteria, name='notification_rule_add_dynamic_criteria'),
    path('rules/<int:rule_id>/delete-criteria/', subscription_rules.notification_rule_delete_criteria, name='notification_rule_delete_criteria'),
    
    # Rule Subscriptions
    path('rules/<int:rule_id>/subscriptions/', subscription_rules.view_rule_subscriptions, name='view_rule_subscriptions'),
]