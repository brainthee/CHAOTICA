from django.contrib import admin
from .models import (
    Notification,
    NotificationSubscription,
    NotificationCategory
)

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["user", "timestamp", "title", "is_emailed"]

@admin.register(NotificationSubscription)
class NotificationSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['user', 'notification_type', 'entity_type', 'entity_id', 'email_enabled', 'in_app_enabled']
    list_filter = ['notification_type', 'entity_type', 'email_enabled', 'in_app_enabled']
    search_fields = ['user__email', 'user__first_name', 'user__last_name']

@admin.register(NotificationCategory)
class NotificationCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'description']