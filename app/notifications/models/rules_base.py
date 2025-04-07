from django.db import models
from django.conf import settings
from notifications.enums import NotificationTypes
from django.utils import timezone
from django.db.models import Q


class SubscriptionRule(models.Model):
    """Defines rules for automatic subscriptions to notifications"""
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    notification_type = models.IntegerField(
        choices=NotificationTypes.CHOICES,
        help_text="Notification type this rule applies to"
    )
    is_active = models.BooleanField(default=True)
    
    # Define rule priority (higher number = higher priority if rules conflict)
    priority = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-priority', 'name']
        verbose_name = "Subscription Rule"
        verbose_name_plural = "Subscription Rules"
    
    def __str__(self):
        return f"{self.name} - {dict(NotificationTypes.CHOICES)[self.notification_type]}"


class BaseRuleCriteria(models.Model):
    """Abstract base class for subscription rule criteria"""
    rule = models.ForeignKey(
        'SubscriptionRule',
        on_delete=models.CASCADE,
        related_name="%(class)s_criteria"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        abstract = True
        
    def get_matching_users(self, entity):
        """Return QuerySet of users matching this criteria for the given entity"""
        raise NotImplementedError("Subclasses must implement this method")



class DynamicRuleCriteria(BaseRuleCriteria):
    """Custom dynamic criteria using callables for more complex logic"""
    criteria_name = models.CharField(max_length=100)
    parameters = models.JSONField(blank=True, null=True, default=dict)
    
    def get_matching_users(self, entity):
        from chaotica_utils.models import User
        # Look up the function from a registry based on criteria_name
        from ..criteria_registry import get_criteria_function
        
        criteria_func = get_criteria_function(self.criteria_name)
        if criteria_func:
            return criteria_func(entity, self.parameters)
        return User.objects.none()
    
    def __str__(self):
        return f"Dynamic Criteria: {self.criteria_name}"