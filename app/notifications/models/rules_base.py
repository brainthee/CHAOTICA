from django.db import models
from notifications.enums import NotificationTypes
from itertools import chain
from .main import NotificationSubscription


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
        choices_dict = dict(NotificationTypes.CHOICES)
        choice_str = choices_dict.get(self.notification_type, f"Unknown ({self.notification_type})")
        return f"{self.name} - {choice_str}"
    
    def save(self, *args, **kwargs):
        """Override save to handle rule updates"""
        is_update = self.pk is not None
        
        # Call the original save method
        super().save(*args, **kwargs)
        
        # If this is an update to an existing rule, we need to update subscriptions
        if is_update and self.is_active:
            self.update_existing_subscriptions()

    def update_existing_subscriptions(self):
        """
        Update all existing subscriptions that were created by this rule.
        This is called when a rule is modified.
        """
        from notifications.utils import apply_rule_to_all_entities, get_entities_by_type_and_ids
        
        # Get all subscriptions created by this rule
        existing_subscriptions = NotificationSubscription.objects.filter(
            created_by_rule=True,
            rule_id=self.id
        )
        
        # Get unique entity identifiers
        entity_types = existing_subscriptions.values_list('entity_type', flat=True).distinct()
        
        # For each entity type, get all IDs and reapply the rule
        for entity_type in entity_types:
            entity_ids = existing_subscriptions.filter(entity_type=entity_type).values_list('entity_id', flat=True).distinct()
            
            # Get the actual entities
            entities = get_entities_by_type_and_ids(entity_type, entity_ids)
            
            # Delete existing subscriptions created by this rule
            existing_subscriptions.filter(entity_type=entity_type).delete()
            
            # Reapply the rule to each entity
            for entity in entities:
                apply_rule_to_all_entities(self, entity)
    
    def get_all_criteria(self):
        """Get all criteria from all related sets"""
        # Combine all criteria types into a single list
        return list(chain(
            self.globalrolecriteria_criteria.all(),
            self.orgunitrolecriteria_criteria.all(),
            self.jobrolecriteria_criteria.all(),
            self.phaserolecriteria_criteria.all(),
            self.phaserolecriteria_criteria.all()
        ))


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
    
    def get_concrete_class(self):
        """Get the most derived class instance"""
        if hasattr(self, 'globalcriteria'):
            return self.globalcriteria
        elif hasattr(self, 'organisationalunitcriteria'):
            return self.organisationalunitcriteria
        elif hasattr(self, 'jobcriteria'):
            return self.jobcriteria
        elif hasattr(self, 'phasecriteria'):
            return self.phasecriteria
        elif hasattr(self, 'phaserolecriteria'):
            return self.phaserolecriteria
        return self
    
    def get_concrete_class_name(self):
        """Get the name of the most derived class"""
        concrete = self.get_concrete_class()
        if concrete:
            return concrete.__class__.__name__
        return self.__class__.__name__
        
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