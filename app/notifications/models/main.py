from django.db import models
from django.conf import settings
from ..enums import NotificationTypes
from constance import config
from django.template.loader import render_to_string
import django.core.mail
import logging

logger = logging.getLogger(__name__)

class NotificationSubscription(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_subscriptions"
    )
    notification_type = models.IntegerField(
        choices=NotificationTypes.CHOICES,
        verbose_name="Notification Type"
    )
    entity_id = models.IntegerField(
        null=True, 
        blank=True,
        help_text="ID of the specific entity (like Job ID, Phase ID) to subscribe to. If empty, subscribes to all of this type."
    )
    entity_type = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        help_text="Type of entity (Job, Phase, etc.)"
    )
    email_enabled = models.BooleanField(default=True)
    in_app_enabled = models.BooleanField(default=True)

    created_by_rule = models.BooleanField(
        default=False,
        help_text="Whether this subscription was created automatically by a rule"
    )
    rule = models.ForeignKey(
        'SubscriptionRule', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="created_subscriptions",
        help_text="The rule that created this subscription"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user', 'notification_type', 'entity_id', 'entity_type')
        verbose_name = "Notification Subscription"
        verbose_name_plural = "Notification Subscriptions"
        
    def __str__(self):
        entity_str = f" for {self.entity_type} #{self.entity_id}" if self.entity_id else ""
        return f"{self.user} - {self.get_notification_type_display()}{entity_str}"

class NotificationOptOut(models.Model):
    """Records when a user has explicitly opted out of a notification"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    notification_type = models.IntegerField(choices=NotificationTypes.CHOICES)
    entity_type = models.CharField(max_length=255)
    entity_id = models.IntegerField()
    opted_out_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user', 'notification_type', 'entity_type', 'entity_id')

class NotificationCategory(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Notification Category"
        verbose_name_plural = "Notification Categories"
        
    def __str__(self):
        return self.name


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    notification_type = models.IntegerField(
        choices=NotificationTypes.CHOICES,
        default=NotificationTypes.SYSTEM
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    title = models.CharField(max_length=255)
    message = models.TextField()
    link = models.URLField(max_length=255, blank=True, null=True)
    read = models.BooleanField(default=False)
    is_emailed = models.BooleanField(default=False)
    should_email = models.BooleanField(default=False)
    email_template = models.CharField(max_length=255, default="")
    entity_id = models.IntegerField(null=True, blank=True)
    entity_type = models.CharField(max_length=100, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    icon = models.CharField(max_length=255, blank=True, null=True, default="")
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.title} - {self.user}"

    def send_email(self, resend=False):
        try:
            if (
                self.user.is_active  # User must be active
                and config.EMAIL_ENABLED  # Emails must be enabled
                and (
                    self.is_emailed == False or resend == True
                )  # Either we've not already sent it or we're resending it
            ):
                context = {
                    'user': self.user,
                    'notification': self,
                    'title': self.title,
                    'message': self.message,
                    'link': self.link,
                    'metadata': self.metadata,
                }
                context["SITE_DOMAIN"] = settings.SITE_DOMAIN
                context["SITE_PROTO"] = settings.SITE_PROTO
                context["title"] = self.title
                context["message"] = self.message
                context["icon"] = self.icon
                context["action_link"] = self.link
                context["user"] = self.user
                msg_html = render_to_string(self.email_template, context)

                django.core.mail.send_mail(
                    subject=context["title"],
                    message=context["message"],
                    from_email=None,
                    recipient_list=[self.user.email_address()],
                    html_message=msg_html,
                    fail_silently=False,
                )

            # Mark it as sent regardless - don't want to create a backlog
            self.is_emailed = True
            self.save()
        except Exception as e:
            logger.error(f"Failed to send email to {self.user.email_address()}: {str(e)}")