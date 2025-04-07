from django.db import models
from django.conf import settings
from notifications.enums import NotificationTypes
from .rules_base import BaseRuleCriteria
from django.utils import timezone
from django.db.models import Q


class GlobalRoleCriteria(BaseRuleCriteria):
    """Subscribe users with specific global roles"""
    from chaotica_utils.enums import GlobalRoles
    
    role = models.IntegerField(choices=GlobalRoles.CHOICES)
    
    def get_matching_users(self, entity):
        from chaotica_utils.models import User
        from django.conf import settings
        
        role_name = settings.GLOBAL_GROUP_PREFIX + self.get_role_display()
        return User.objects.filter(
            groups__name=role_name,
            is_active=True
        )
    
    def __str__(self):
        return f"Global Role: {self.get_role_display()}"


class OrgUnitRoleCriteria(BaseRuleCriteria):
    """Subscribe users with specific roles in an org unit"""
    unit_role = models.ForeignKey('jobtracker.OrganisationalUnitRole', on_delete=models.CASCADE)
    
    def get_matching_users(self, entity):
        from chaotica_utils.models import User
        
        # Get the appropriate org unit based on entity type
        unit = None
        if hasattr(entity, 'unit'):
            unit = entity.unit
        elif hasattr(entity, 'job') and hasattr(entity.job, 'unit'):
            unit = entity.job.unit
            
        if unit:
            return User.objects.filter(
                unit_memberships__unit=unit,
                unit_memberships__role=self.unit_role,
                is_active=True
            )
        return User.objects.none()
    
    def __str__(self):
        return f"Org Unit Role: {self.unit_role.name}"


class JobRoleCriteria(BaseRuleCriteria):
    """Subscribe users with specific roles on a job"""
    JOB_ROLES = (
        (0, "Account Manager"),
        (1, "Deputy Account Manager"),
        (2, "Created By"),
        (3, "Primary Point of Contact"),
    )
    
    role_id = models.IntegerField()
    
    @property
    def role_display(self):
        role_dict = dict(self.JOB_ROLES)
        return role_dict.get(self.role_id, "Unknown")
    
    def get_matching_users(self, entity):
        from chaotica_utils.models import User
        
        job = entity if hasattr(entity, 'account_manager') else getattr(entity, 'job', None)
        if job:
            if self.role_id == 0:  # Account Manager
                return User.objects.filter(pk=job.account_manager.pk, is_active=True) if job.account_manager else User.objects.none()
            elif self.role_id == 1:  # Deputy Account Manager
                return User.objects.filter(pk=job.dep_account_manager.pk, is_active=True) if job.dep_account_manager else User.objects.none()
            elif self.role_id == 2:  # Created By
                return User.objects.filter(pk=job.created_by.pk, is_active=True) if job.created_by else User.objects.none()
            elif self.role_id == 3:  # Primary Point of Contact
                return User.objects.filter(pk=job.primary_poc.pk, is_active=True) if hasattr(job, 'primary_poc') and job.primary_poc else User.objects.none()
        
        return User.objects.none()
    
    def __str__(self):
        return f"Job Role: {self.role_display}"


class PhaseRoleCriteria(BaseRuleCriteria):
    """Subscribe users with specific roles on a phase"""
    PHASE_ROLES = (
        (0, "Project Lead"),
        (1, "Report Author"),
        (2, "TQA Reviewer"),
        (3, "PQA Reviewer"),
    )
    
    role_id = models.IntegerField()
    
    @property
    def role_display(self):
        role_dict = dict(self.PHASE_ROLES)
        return role_dict.get(self.role_id, "Unknown")
    
    def get_matching_users(self, entity):
        from chaotica_utils.models import User
        
        phase = entity if hasattr(entity, 'project_lead') else None
        if phase:
            if self.role_id == 0:  # Project Lead
                return User.objects.filter(pk=phase.project_lead.pk, is_active=True) if phase.project_lead else User.objects.none()
            elif self.role_id == 1:  # Report Author
                return User.objects.filter(pk=phase.report_author.pk, is_active=True) if phase.report_author else User.objects.none()
            elif self.role_id == 2:  # TQA Reviewer
                return User.objects.filter(pk=phase.tech_reviewer.pk, is_active=True) if hasattr(phase, 'tech_reviewer') and phase.tech_reviewer else User.objects.none()
            elif self.role_id == 3:  # PQA Reviewer
                return User.objects.filter(pk=phase.pres_reviewer.pk, is_active=True) if hasattr(phase, 'pres_reviewer') and phase.pres_reviewer else User.objects.none()
            
        return User.objects.none()
    
    def __str__(self):
        return f"Phase Role: {self.role_display}"