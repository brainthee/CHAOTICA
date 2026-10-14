from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from .models import Report, DataArea, DataField

def can_view_report(user, report):
    """
    Check if user can view a report
    """
    if user.is_superuser:
        return True
    
    if report.owner == user:
        return True
    
    if not report.is_private:
        # Public reports can be viewed by anyone with basic permissions
        if user.has_perm('reporting.view_report'):
            return True
    
    # Check if user has special permission to view all reports
    if user.has_perm('reporting.can_run_all_reports'):
        return True
    
    return False

def can_edit_report(user, report):
    """
    Check if user can edit a report
    """
    if user.is_superuser:
        return True
    
    if report.owner == user:
        return True
    
    # Check if user has special permission to edit all reports
    if user.has_perm('reporting.change_report'):
        return True
    
    return False

def can_create_report(user):
    """
    Check if user can create reports
    """
    if user.is_superuser:
        return True
    
    # Check if user has permission to create reports
    if user.has_perm('reporting.add_report'):
        return True
    
    return False

def can_delete_report(user, report):
    """
    Check if user can delete a report
    """
    if user.is_superuser:
        return True
    
    if report.owner == user:
        return True
    
    # Check if user has special permission to delete all reports
    if user.has_perm('reporting.delete_report'):
        return True
    
    return False

def can_share_report(user, report):
    """
    Check if user can share/make public a report
    """
    if user.is_superuser:
        return True
    
    if report.owner == user and user.has_perm('reporting.can_share_reports'):
        return True
    
    return False

def can_run_as_anyone(user):
    """Whether ``user`` may schedule a report to run as any (non-superuser)."""
    return (
        user.is_superuser
        or user.has_perm('reporting.can_run_all_reports')
        or user.has_perm('chaotica_utils.manage_user')
    )


def run_as_candidates(user):
    """Users a scheduled report created by ``user`` may run as: themselves, the
    people they (acting-)manage, or anyone for ``can_run_as_anyone`` holders.
    Superusers and inactive accounts are never valid targets."""
    from django.db.models import Q
    from chaotica_utils.models import User

    qs = User.objects.filter(is_active=True, is_superuser=False)
    if not can_run_as_anyone(user):
        qs = qs.filter(Q(pk=user.pk) | Q(manager=user) | Q(acting_manager=user))
    return qs.order_by('first_name', 'last_name')


def is_internal_recipient(address, known_emails=None):
    """True if ``address`` belongs to an active user, or its domain is on the
    ALLOWED_SIGNUP_EMAIL_DOMAINS allowlist (a blank allowlist allows none)."""
    from django.db.models import Q
    from chaotica_utils.utils import get_allowed_signup_email_domains
    from chaotica_utils.models import User

    address = (address or '').strip().lower()
    if '@' not in address:
        return False
    if known_emails is not None:
        if address in known_emails:
            return True
    elif User.objects.filter(is_active=True).filter(
        Q(email__iexact=address) | Q(notification_email__iexact=address)
    ).exists():
        return True
    allowed = get_allowed_signup_email_domains()
    return bool(allowed) and address.rsplit('@', 1)[1] in allowed


def can_access_data_area(user, data_area):
    """
    Check if user can access a data area
    """
    if user.is_superuser:
        return True
    
    # Check for model-specific permissions
    model_name = data_area.model_name.lower()
    if user.has_perm(f'{data_area.content_type.app_label}.view_{model_name}'):
        return True
    
    return False

def can_use_field(user, field):
    """
    Check if user can use a specific field in reports
    """
    if user.is_superuser:
        return True
    
    # Check if field is sensitive and requires specific permission
    if field.is_sensitive and field.requires_permission:
        return user.has_perm(field.requires_permission)
    
    # Check if user can access the data area
    return can_access_data_area(user, field.data_area)


class ReportAccessMixin(UserPassesTestMixin):
    """
    Mixin for checking if a user can access a report
    """
    
    def test_func(self):
        report = self.get_object()
        return can_view_report(self.request.user, report)
    
    def handle_no_permission(self):
        raise PermissionDenied("You don't have permission to access this report.")


class ReportEditMixin(UserPassesTestMixin):
    """
    Mixin for checking if a user can edit a report
    """
    
    def test_func(self):
        report = self.get_object()
        return can_edit_report(self.request.user, report)
    
    def handle_no_permission(self):
        raise PermissionDenied("You don't have permission to edit this report.")


class ReportDeleteMixin(UserPassesTestMixin):
    """
    Mixin for checking if a user can delete a report
    """
    
    def test_func(self):
        report = self.get_object()
        return can_delete_report(self.request.user, report)
    
    def handle_no_permission(self):
        raise PermissionDenied("You don't have permission to delete this report.")


class ReportCreatePermissionMixin(UserPassesTestMixin):
    """
    Mixin for checking if a user can create reports
    """
    
    def test_func(self):
        return can_create_report(self.request.user)
    
    def handle_no_permission(self):
        raise PermissionDenied("You don't have permission to create reports.")