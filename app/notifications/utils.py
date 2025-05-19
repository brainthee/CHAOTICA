from .models import (
    NotificationSubscription,
    Notification,
    NotificationOptOut,
    SubscriptionRule,
)
from django.conf import settings as django_settings
from django.utils import timezone
from chaotica_utils.utils import ext_reverse
from jobtracker.enums import JobStatuses, PhaseStatuses
from django.db.models import QuerySet
from .enums import NotificationTypes


class AppNotification:
    def __init__(
        self,
        notification_type,
        title,
        message="",
        email_template=None,
        metadata=None,
        link=None,
        entity_type=None,
        entity_id=None,
        **kwargs,
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
            ).values_list("user__id", flat=True)
        else:
            specific_subscribers = []

        # Combine both sets
        subscriber_ids = set(specific_subscribers)  # | set(general_subscribers)

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
            ).values_list("user__id", flat=True)
        else:
            specific_subscribers = []

        # general_subscribers = NotificationSubscription.objects.filter(
        #     notification_type=self.notification_type,
        #     entity_id__isnull=True,
        #     email_enabled=True,
        # ).values_list("user_id", flat=True)

        subscriber_ids = set(specific_subscribers)  # | set(general_subscribers)

        return User.objects.filter(id__in=subscriber_ids, is_active=True)


def send_notifications(notification, specific_users=None, extra_recipients=None):
    """
    Send notifications to users

    Args:
        notification (AppNotification): Notification to send
        specific_users (User or QuerySet, optional): Specific user or users to notify. If None, uses subscription system.
    """
    from chaotica_utils.views.common import log_system_activity

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

    choices_dict = dict(NotificationTypes.CHOICES)
    notification_type_name = choices_dict.get(
        notification.notification_type, "Unknown"
    )
    entity = get_entity_object(
        entity_id=notification.entity_id, entity_type=notification.entity_type
    )

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
            # metadata=notification.metadata,
            email_template=notification.email_template or "",
            should_email=user in email_recipients,
        )
        # Lets create the note
        log_system_activity(
            entity,
            "{notification_type_name} notification sent to {target}".format(
                notification_type_name=notification_type_name,
                target=user.email_address(),
            ),
        )


def auto_subscribe_users(notification_type, entity):
    """Auto-subscribe users based on rules, respecting opt-outs"""
    # Get applicable rules
    rules = SubscriptionRule.objects.filter(
        notification_type=notification_type, is_active=True
    ).prefetch_related(
        "globalrolecriteria_criteria",
        "orgunitrolecriteria_criteria",
        "jobrolecriteria_criteria",
        "phaserolecriteria_criteria",
        "dynamicrulecriteria_criteria",
    )

    if not rules.exists():
        return

    entity_type = entity.__class__.__name__
    entity_id = entity.id

    # Filter out users who have opted out
    opted_out_users = NotificationOptOut.objects.filter(
        notification_type=notification_type,
        entity_type=entity_type,
        entity_id=entity_id,
    ).values_list("user__id", flat=True)

    # Get currently subscribed users
    currently_subscribed = NotificationSubscription.objects.filter(
        notification_type=notification_type,
        entity_type=entity_type,
        entity_id=entity_id,
        created_by_rule=True,  # Only consider rule-based subscriptions
    ).values_list("user__id", flat=True)

    # Compile all matching users from all rules
    subscribed_users = set()
    for rule in rules:
        # Process each type of criteria
        for criteria_type in [
            "globalrolecriteria",
            "orgunitrolecriteria",
            "jobrolecriteria",
            "phaserolecriteria",
            "dynamicrulecriteria",
        ]:
            criteria_manager = getattr(rule, f"{criteria_type}_criteria", None)
            if not criteria_manager:
                continue

            for criteria in criteria_manager.all():
                matching_users = criteria.get_matching_users(entity)
                for user in matching_users:
                    subscribed_users.add(user)

    # Users to add: matching users who aren't opted out or already subscribed
    users_to_add = [
        user
        for user in subscribed_users
        if user.id not in opted_out_users and user.id not in currently_subscribed
    ]

    # Users to remove: currently subscribed who no longer match and were rule-created
    users_to_remove = [
        user_id
        for user_id in currently_subscribed
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
                created_by_rule=True,
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
            created_by_rule=True,
        ).delete()


def reassign_manager_subscriptions(user, old_manager, new_manager):
    """
    Reassign all subscriptions from old_manager to new_manager
    for notifications related to the specified user
    """
    if old_manager == new_manager:
        return  # No change needed

    # Get all entity types and IDs where the old manager has subscriptions related to this user
    from notifications.models import NotificationSubscription
    from chaotica_utils.models import LeaveRequest

    # For leave requests
    leave_requests = LeaveRequest.objects.filter(user=user)
    for leave_request in leave_requests:
        # Get all subscriptions for the old manager
        old_subs = NotificationSubscription.objects.filter(
            entity_type="leave_request", entity_id=leave_request.id, user=old_manager
        )

        # For each subscription type the old manager had
        for sub in old_subs:
            # Create equivalent for new manager if it doesn't exist
            NotificationSubscription.objects.get_or_create(
                notification_type=sub.notification_type,
                entity_type=sub.entity_type,
                entity_id=sub.entity_id,
                user=new_manager,
                defaults={"created_by_rule": True, "created_at": timezone.now()},
            )

        # Remove old manager's subscriptions
        old_subs.delete()


def get_entity_object(entity_type, entity_id):
    try:
        if entity_type == "LeaveRequest":
            from chaotica_utils.models import LeaveRequest
            return LeaveRequest.objects.get(id=entity_id)
        elif entity_type == "Job":
            from jobtracker.models import Job
            return Job.objects.get(id=entity_id)
        elif entity_type == "Phase":
            from jobtracker.models import Phase
            return Phase.objects.get(id=entity_id)
        elif entity_type == "User":
            from chaotica_utils.models import User
            return User.objects.get(pk=entity_id)
    except:
        return None
    # Add more as needed
    return None


def get_all_entities_by_type(entity_type):
    """Get all entities of a particular type"""
    if entity_type == "LeaveRequest":
        from chaotica_utils.models import LeaveRequest

        # Might want to filter to only active/recent leave requests
        return LeaveRequest.objects.filter(cancelled=False, declined=False)
    elif entity_type == "Job":
        from jobtracker.models import Job

        # Might want to filter to only active jobs
        return Job.objects.filter(
            status__in=JobStatuses.ACTIVE_STATUSES
        )  # Assuming these are active statuses
    elif entity_type == "Phase":
        from jobtracker.models import Phase

        # Might want to filter to only active phases
        return Phase.objects.filter(
            status__in=PhaseStatuses.ACTIVE_STATUSES
        )  # Assuming these are active statuses
    # Add more as needed
    return []


def get_entities_by_type_and_ids(entity_type, entity_ids):
    """Get entities based on their type and IDs"""
    if entity_type == "LeaveRequest":
        from chaotica_utils.models import LeaveRequest

        return LeaveRequest.objects.filter(id__in=entity_ids)
    elif entity_type == "Job":
        from jobtracker.models import Job

        return Job.objects.filter(id__in=entity_ids)
    elif entity_type == "Phase":
        from jobtracker.models import Phase

        return Phase.objects.filter(id__in=entity_ids)
    elif entity_type == "Project":
        from jobtracker.models import Project
        return Project.objects.filter(id__in=entity_ids)
    # Add more entity types as needed
    return []


def apply_rule_to_entity(rule, entity):
    """Apply a single subscription rule to a single entity"""
    # Get all users that should be subscribed according to the rule
    matching_users = []

    # Process each criteria
    for criteria in rule.globalrolecriteria_criteria.all():
        users = criteria.get_matching_users(entity)
        matching_users.extend(users)
    for criteria in rule.orgunitrolecriteria_criteria.all():
        users = criteria.get_matching_users(entity)
        matching_users.extend(users)
    for criteria in rule.jobrolecriteria_criteria.all():
        users = criteria.get_matching_users(entity)
        matching_users.extend(users)
    for criteria in rule.phaserolecriteria_criteria.all():
        users = criteria.get_matching_users(entity)
        matching_users.extend(users)
    for criteria in rule.dynamicrulecriteria_criteria.all():
        users = criteria.get_matching_users(entity)
        matching_users.extend(users)

    # Remove duplicates
    matching_users = list(set(matching_users))

    # Create subscriptions for matching users
    for user in matching_users:
        NotificationSubscription.objects.get_or_create(
            notification_type=rule.notification_type,
            entity_type=entity.__class__.__name__,
            entity_id=entity.id,
            user=user,
            defaults={
                "created_by_rule": True,
                "rule_id": rule.id,
                "created_at": timezone.now(),
            },
        )


def apply_rule_to_all_entities(rule, entity_type=None):
    """Apply a rule to all relevant entities (or entities of a specific type)"""
    if not rule.is_active:
        return

    # Define which entity types to process based on the notification type
    notification_type = rule.notification_type

    entity_types_to_process = []

    # If a specific entity type was requested, only process that one
    if entity_type:
        entity_types_to_process = [entity_type]
    else:
        # Otherwise determine which types to process based on notification type
        if notification_type in NotificationTypes.LEAVE_EVENTS:
            entity_types_to_process.append("LeaveRequest")

        if notification_type in NotificationTypes.JOB_EVENTS:
            entity_types_to_process.append("Job")

        if notification_type in NotificationTypes.PHASE_EVENTS:
            entity_types_to_process.append("Phase")

    # Process each entity type
    for entity_type in entity_types_to_process:
        entities = get_all_entities_by_type(entity_type)

        for entity in entities:
            apply_rule_to_entity(rule, entity)
