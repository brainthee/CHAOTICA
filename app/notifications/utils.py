from .models import NotificationSubscription, Notification, NotificationOptOut, SubscriptionRule
from django.conf import settings as django_settings
from chaotica_utils.utils import ext_reverse
from django.db.models import QuerySet


class AppNotification:
    def __init__(
        self,
        notification_type,
        title,
        message,
        email_template=None,
        metadata=None,
        link=None,
        entity_type=None,
        entity_id=None,
        **kwargs
    ):
        self.notification_type = notification_type
        self.title = title
        self.message = message
        self.email_template = email_template
        self.metadata = metadata or {}
        if link:
            # Check if it needs to be made external
            if not link.startswith(
                "{}://{}".format(
                    django_settings.SITE_PROTO, django_settings.SITE_DOMAIN
                )
            ):
                self.action_link = ext_reverse(link)
            else:
                self.action_link = link
        else:
            self.action_link = None
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.metadata.update(kwargs)


    def get_subscribers(self):
        """Get all users who should receive this notification"""
        from chaotica_utils.models.user import User
        # Start with specific entity subscriptions
        if self.entity_id and self.entity_type:
            specific_subscribers = NotificationSubscription.objects.filter(
                notification_type=self.notification_type,
                entity_id=self.entity_id,
                entity_type=self.entity_type,
                in_app_enabled=True,
            ).values_list("user_id", flat=True)
        else:
            specific_subscribers = []

        # For now ignore the "sub to any/all notifications" - we don't want to support this.

        # # Then get users subscribed to all notifications of this type
        # general_subscribers = NotificationSubscription.objects.filter(
        #     notification_type=self.notification_type,
        #     entity_id__isnull=True,
        #     in_app_enabled=True,
        # ).values_list("user_id", flat=True)

        # Combine both sets
        subscriber_ids = set(specific_subscribers) #| set(general_subscribers)

        return User.objects.filter(id__in=subscriber_ids, is_active=True)

    def get_email_subscribers(self):
        """Get all users who should receive this notification by email"""
        from chaotica_utils.models.user import User

        # Similar to get_subscribers but checking email_enabled
        if self.entity_id and self.entity_type:
            specific_subscribers = NotificationSubscription.objects.filter(
                notification_type=self.notification_type,
                entity_id=self.entity_id,
                entity_type=self.entity_type,
                email_enabled=True,
            ).values_list("user_id", flat=True)
        else:
            specific_subscribers = []

        # general_subscribers = NotificationSubscription.objects.filter(
        #     notification_type=self.notification_type,
        #     entity_id__isnull=True,
        #     email_enabled=True,
        # ).values_list("user_id", flat=True)

        subscriber_ids = set(specific_subscribers) #| set(general_subscribers)

        return User.objects.filter(id__in=subscriber_ids, is_active=True)


def send_notifications(notification, specific_users=None):
    """
    Send notifications to users
    
    Args:
        notification (AppNotification): Notification to send
        specific_users (User or QuerySet, optional): Specific user or users to notify. If None, uses subscription system.
    """
    
    # Determine recipients
    if specific_users is not None:
        # Legacy usage: specific users were provided
        if isinstance(specific_users, QuerySet):
            recipients = specific_users
        else:
            recipients = [specific_users]
    else:
        # Use the subscription system
        recipients = notification.get_subscribers()
    
    email_recipients = []
    if notification.email_template:
        if specific_users is not None:
            # Legacy usage
            email_recipients = recipients
        else:
            # Use subscription system for emails
            email_recipients = notification.get_email_subscribers()
    
    # Create in-app notifications
    for user in recipients:
        _ = Notification.objects.create(
            user=user,
            notification_type=notification.notification_type,
            title=notification.title,
            message=notification.message,
            link=notification.action_link,
            entity_id=notification.entity_id,
            entity_type=notification.entity_type,
            metadata=notification.metadata,
            email_template=notification.email_template or "",
            should_email=user in email_recipients,
        )


def auto_subscribe_users(notification_type, entity):
    """Auto-subscribe users based on rules, respecting opt-outs"""    
    # Get applicable rules
    rules = SubscriptionRule.objects.filter(
        notification_type=notification_type,
        is_active=True
    ).prefetch_related(
        'globalrolecriteria_criteria',
        'orgunitrolecriteria_criteria',
        'jobrolecriteria_criteria',
        'phaserolecriteria_criteria',
        'dynamicrulecriteria_criteria'
    )
    
    if not rules.exists():
        return
    
    entity_type = entity._meta.model_name
    entity_id = entity.id
    
    # Filter out users who have opted out
    opted_out_users = NotificationOptOut.objects.filter(
        notification_type=notification_type,
        entity_type=entity_type,
        entity_id=entity_id
    ).values_list('user_id', flat=True)
    
    # Get currently subscribed users
    currently_subscribed = NotificationSubscription.objects.filter(
        notification_type=notification_type,
        entity_type=entity_type,
        entity_id=entity_id,
        created_by_rule=True  # Only consider rule-based subscriptions
    ).values_list('user_id', flat=True)

    # Compile all matching users from all rules
    subscribed_users = set()
    for rule in rules:
        # Process each type of criteria
        for criteria_type in ['globalrolecriteria', 'orgunitrolecriteria', 'jobrolecriteria', 'dynamicrulecriteria']:
            criteria_manager = getattr(rule, f"{criteria_type}_criteria", None)
            if not criteria_manager:
                continue
                
            for criteria in criteria_manager.all():
                matching_users = criteria.get_matching_users(entity)
                for user in matching_users:
                    subscribed_users.add(user)

    
    # Users to add: matching users who aren't opted out or already subscribed
    users_to_add = [
        user for user in subscribed_users 
        if user.id not in opted_out_users and user.id not in currently_subscribed
    ]
    
    # Users to remove: currently subscribed who no longer match and were rule-created
    users_to_remove = [
        user_id for user_id in currently_subscribed 
        if user_id not in [u.id for u in subscribed_users]
    ]
    
    # Add new subscriptions
    bulk_create_list = []
    for user in users_to_add:
        bulk_create_list.append(
            NotificationSubscription(
                user=user,
                notification_type=notification_type,
                entity_type=entity_type,
                entity_id=entity_id,
                email_enabled=True,
                in_app_enabled=True,
                created_by_rule=True
            )
        )
    
    if bulk_create_list:
        NotificationSubscription.objects.bulk_create(bulk_create_list)
    
    # Remove outdated subscriptions
    if users_to_remove:
        NotificationSubscription.objects.filter(
            user_id__in=users_to_remove,
            notification_type=notification_type,
            entity_type=entity_type,
            entity_id=entity_id,
            created_by_rule=True
        ).delete()