from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse, HttpResponseRedirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from ..models import (
    Notification, 
    NotificationSubscription, 
    NotificationCategory,
    SubscriptionRule,
    GlobalRoleCriteria,
    OrgUnitRoleCriteria,
    JobRoleCriteria,
    PhaseRoleCriteria,
    DynamicRuleCriteria
)
from ..enums import NotificationTypes
from ..forms import (
    SubscriptionRuleForm, 
    GlobalRoleCriteriaForm,
    OrgUnitRoleCriteriaForm,
    JobRoleCriteriaForm,
    PhaseRoleCriteriaForm,
    DynamicRuleCriteriaForm
)
from ..criteria_registry import _CRITERIA_REGISTRY

# Existing notification views...

@login_required
@permission_required('notifications.view_subscriptionrule')
def notification_rules(request):
    """List all subscription rules"""
    filter_type = request.GET.get('type')
    filter_active = request.GET.get('active')
    
    rules = SubscriptionRule.objects.all().prefetch_related(
        'globalrolecriteria_criteria',
        'orgunitrolecriteria_criteria',
        'jobrolecriteria_criteria',
        'dynamicrulecriteria_criteria'
    )
    
    # Apply filters
    if filter_type:
        try:
            filter_type = int(filter_type)
            rules = rules.filter(notification_type=filter_type)
        except (ValueError, TypeError):
            pass
    
    if filter_active:
        if filter_active == '1':
            rules = rules.filter(is_active=True)
        elif filter_active == '0':
            rules = rules.filter(is_active=False)
    
    # Order by priority (desc) and name
    rules = rules.order_by('-priority', 'name')
    
    # Paginate the results
    paginator = Paginator(rules, 10)
    page_number = request.GET.get('page')
    rules = paginator.get_page(page_number)
    
    context = {
        'rules': rules,
        'notification_types': NotificationTypes.CHOICES,
        'filter_type': filter_type,
        'filter_active': filter_active,
    }
    
    return render(request, 'notification_rules/list.html', context)

@login_required
@permission_required('notifications.view_subscriptionrule')
def notification_rule_detail(request, rule_id):
    """View a specific subscription rule"""
    rule = get_object_or_404(SubscriptionRule, id=rule_id)
    
    # Get all criteria
    global_criteria = rule.globalrolecriteria_criteria.all()
    org_criteria = rule.orgunitrolecriteria_criteria.all().select_related('unit_role')
    job_criteria = rule.jobrolecriteria_criteria.all()
    phase_criteria = rule.phaserolecriteria_criteria.all()
    dynamic_criteria = rule.dynamicrulecriteria_criteria.all()
    
    # Get subscription statistics
    subscriptions = NotificationSubscription.objects.filter(
        notification_type=rule.notification_type,
        created_by_rule=True
    )
    
    subscription_count = subscriptions.count()
    unique_users = subscriptions.values('user').distinct().count()
    entity_count = subscriptions.values('entity_type', 'entity_id').distinct().count()
    email_enabled_count = subscriptions.filter(email_enabled=True).count()
    
    # Get recent subscriptions
    recent_subscriptions = subscriptions.select_related('user').order_by('-created_at')[:5]
    
    context = {
        'rule': rule,
        'global_criteria': global_criteria,
        'org_criteria': org_criteria,
        'job_criteria': job_criteria,
        'phase_criteria': phase_criteria,
        'dynamic_criteria': dynamic_criteria,
        'subscription_count': subscription_count,
        'unique_users': unique_users,
        'entity_count': entity_count,
        'email_enabled_count': email_enabled_count,
        'recent_subscriptions': recent_subscriptions,
    }
    
    return render(request, 'notification_rules/detail.html', context)

@login_required
@permission_required('notifications.add_subscriptionrule')
def notification_rule_create(request):
    """Create a new subscription rule"""
    if request.method == 'POST':
        form = SubscriptionRuleForm(request.POST)
        if form.is_valid():
            rule = form.save()
            messages.success(request, f"Subscription rule '{rule.name}' created successfully")
            return redirect('notification_rule_detail', rule_id=rule.id)
    else:
        form = SubscriptionRuleForm()
    
    # Prepare notification type descriptions
    type_descriptions = {
        NotificationTypes.SYSTEM: "System-generated notifications",
        NotificationTypes.JOB_STATUS_CHANGE: "When a job's status changes",
        NotificationTypes.JOB_CREATED: "When a new job is created",
        NotificationTypes.PHASE_STATUS_CHANGE: "When a phase's status changes",
        NotificationTypes.PHASE_LATE_TO_TQA: "When a phase is late for TQA",
        NotificationTypes.PHASE_LATE_TO_PQA: "When a phase is late for PQA",
        NotificationTypes.PHASE_TQA_UPDATES: "Updates related to TQA of a phase",
        NotificationTypes.PHASE_PQA_UPDATES: "Updates related to PQA of a phase",
        NotificationTypes.PHASE_LATE_TO_DELIVERY: "When a phase is late for delivery",
        NotificationTypes.PHASE_NEW_NOTE: "When a note is added to a phase",
        NotificationTypes.PHASE_FEEDBACK: "When feedback is added to a phase",
        NotificationTypes.LEAVE_SUBMITTED: "When leave is submitted",
        NotificationTypes.LEAVE_APPROVED: "When leave is approved",
        NotificationTypes.LEAVE_REJECTED: "When leave is rejected",
        NotificationTypes.LEAVE_CANCELLED: "When leave is cancelled",
        NotificationTypes.CLIENT_ONBOARDING_RENEWAL: "Client onboarding renewal reminders",
    }
    
    context = {
        'form': form,
        'notification_types': NotificationTypes.CHOICES,
        'type_descriptions': type_descriptions,
    }
    
    return render(request, 'notification_rules/form.html', context)

@login_required
@permission_required('notifications.change_subscriptionrule')
def notification_rule_edit(request, rule_id):
    """Edit an existing subscription rule"""
    rule = get_object_or_404(SubscriptionRule, id=rule_id)
    
    if request.method == 'POST':
        form = SubscriptionRuleForm(request.POST, instance=rule)
        if form.is_valid():
            rule = form.save()
            messages.success(request, f"Subscription rule '{rule.name}' updated successfully")
            return redirect('notification_rule_detail', rule_id=rule.id)
    else:
        form = SubscriptionRuleForm(instance=rule)
    
    # Prepare notification type descriptions
    type_descriptions = {
        NotificationTypes.SYSTEM: "System-generated notifications",
        NotificationTypes.JOB_STATUS_CHANGE: "When a job's status changes",
        NotificationTypes.JOB_CREATED: "When a new job is created",
        NotificationTypes.PHASE_STATUS_CHANGE: "When a phase's status changes",
        NotificationTypes.PHASE_LATE_TO_TQA: "When a phase is late for TQA",
        NotificationTypes.PHASE_LATE_TO_PQA: "When a phase is late for PQA",
        NotificationTypes.PHASE_TQA_UPDATES: "Updates related to TQA of a phase",
        NotificationTypes.PHASE_PQA_UPDATES: "Updates related to PQA of a phase",
        NotificationTypes.PHASE_LATE_TO_DELIVERY: "When a phase is late for delivery",
        NotificationTypes.PHASE_NEW_NOTE: "When a note is added to a phase",
        NotificationTypes.PHASE_FEEDBACK: "When feedback is added to a phase",
        NotificationTypes.LEAVE_SUBMITTED: "When leave is submitted",
        NotificationTypes.LEAVE_APPROVED: "When leave is approved",
        NotificationTypes.LEAVE_REJECTED: "When leave is rejected",
        NotificationTypes.LEAVE_CANCELLED: "When leave is cancelled",
        NotificationTypes.CLIENT_ONBOARDING_RENEWAL: "Client onboarding renewal reminders",
    }
    
    context = {
        'form': form,
        'rule': rule,
        'notification_types': NotificationTypes.CHOICES,
        'type_descriptions': type_descriptions,
    }
    
    return render(request, 'notification_rules/form.html', context)

@login_required
@permission_required('notifications.delete_subscriptionrule')
def notification_rule_delete(request, rule_id):
    """Delete a subscription rule"""
    rule = get_object_or_404(SubscriptionRule, id=rule_id)
    rule_name = rule.name
    
    # Delete the rule
    rule.delete()
    
    messages.success(request, f"Subscription rule '{rule_name}' deleted successfully")
    return redirect('notification_rules')

@login_required
@permission_required('notifications.change_subscriptionrule')
def notification_rule_toggle(request, rule_id):
    """Toggle a rule's active status"""
    rule = get_object_or_404(SubscriptionRule, id=rule_id)
    
    # Toggle the active status
    rule.is_active = not rule.is_active
    rule.save()
    
    if rule.is_active:
        messages.success(request, f"Subscription rule '{rule.name}' activated")
    else:
        messages.info(request, f"Subscription rule '{rule.name}' deactivated")
    
    return redirect('notification_rule_detail', rule_id=rule.id)

@login_required
@permission_required('notifications.change_subscriptionrule')
def notification_rule_add_criteria(request, rule_id):
    """Add criteria to a subscription rule"""
    rule = get_object_or_404(SubscriptionRule, id=rule_id)
    
    # Create forms for each criteria type
    global_form = GlobalRoleCriteriaForm()
    org_form = OrgUnitRoleCriteriaForm()
    job_form = JobRoleCriteriaForm()
    phase_form = PhaseRoleCriteriaForm()
    dynamic_form = DynamicRuleCriteriaForm()
    
    # Get choices for the job/phase role selects
    job_roles = JobRoleCriteria.JOB_ROLES
    phase_roles = PhaseRoleCriteria.PHASE_ROLES
    
    # Get available dynamic criteria
    available_criteria = [(name, name) for name in _CRITERIA_REGISTRY.keys()]
    dynamic_form.fields['criteria_name'].choices = available_criteria
    
    context = {
        'rule': rule,
        'global_form': global_form,
        'org_form': org_form,
        'job_form': job_form,
        'phase_form': phase_form,
        'dynamic_form': dynamic_form,
        'job_roles': job_roles,
        'phase_roles': phase_roles,
    }
    
    return render(request, 'notification_rules/add_criteria.html', context)

@login_required
@permission_required('notifications.change_subscriptionrule')
@require_POST
def notification_rule_add_global_criteria(request, rule_id):
    """Add a global role criteria to a rule"""
    rule = get_object_or_404(SubscriptionRule, id=rule_id)
    
    form = GlobalRoleCriteriaForm(request.POST)
    if form.is_valid():
        criteria = form.save(commit=False)
        criteria.rule = rule
        criteria.save()
        
        messages.success(request, "Global role criteria added successfully")
    else:
        messages.error(request, "Failed to add global role criteria")
    
    return redirect('notification_rule_detail', rule_id=rule.id)

@login_required
@permission_required('notifications.change_subscriptionrule')
@require_POST
def notification_rule_add_org_criteria(request, rule_id):
    """Add an organizational unit role criteria to a rule"""
    rule = get_object_or_404(SubscriptionRule, id=rule_id)
    
    form = OrgUnitRoleCriteriaForm(request.POST)
    if form.is_valid():
        criteria = form.save(commit=False)
        criteria.rule = rule
        criteria.save()
        
        messages.success(request, "Organizational unit role criteria added successfully")
    else:
        messages.error(request, "Failed to add organizational unit role criteria")
    
    return redirect('notification_rule_detail', rule_id=rule.id)

@login_required
@permission_required('notifications.change_subscriptionrule')
@require_POST
def notification_rule_add_job_criteria(request, rule_id):
    """Add a job/phase role criteria to a rule"""
    rule = get_object_or_404(SubscriptionRule, id=rule_id)
    
    # Get form data
    role_id = request.POST.get('role_id')
    
    try:
        role_id = int(role_id)
        
        # Validate role_id
        if role_id >= len(JobRoleCriteria.JOB_ROLES):
            messages.error(request, "Invalid job role")
            return redirect('notification_rule_add_criteria', rule_id=rule.id)
        
        # Create the criteria
        JobRoleCriteria.objects.create(
            rule=rule,
            role_id=role_id
        )
        
        messages.success(request, "Job/phase role criteria added successfully")
    except (ValueError, TypeError):
        messages.error(request, "Invalid role ID")
    
    return redirect('notification_rule_detail', rule_id=rule.id)


@login_required
@permission_required('notifications.change_subscriptionrule')
@require_POST
def notification_rule_add_phase_criteria(request, rule_id):
    """Add a phase role criteria to a rule"""
    rule = get_object_or_404(SubscriptionRule, id=rule_id)
    
    # Get form data
    role_id = request.POST.get('role_id')
    
    try:
        role_id = int(role_id)
        
        if role_id >= len(PhaseRoleCriteria.PHASE_ROLES):
            messages.error(request, "Invalid phase role")
            return redirect('notification_rule_add_criteria', rule_id=rule.id)
        
        # Create the criteria
        PhaseRoleCriteria.objects.create(
            rule=rule,
            role_id=role_id
        )
        
        messages.success(request, "Phase role criteria added successfully")
    except (ValueError, TypeError):
        messages.error(request, "Invalid role ID")
    
    return redirect('notification_rule_detail', rule_id=rule.id)

@login_required
@permission_required('notifications.change_subscriptionrule')
@require_POST
def notification_rule_add_dynamic_criteria(request, rule_id):
    """Add a dynamic criteria to a rule"""
    rule = get_object_or_404(SubscriptionRule, id=rule_id)
    
    form = DynamicRuleCriteriaForm(request.POST)
    form.fields['criteria_name'].choices = [(name, name) for name in _CRITERIA_REGISTRY.keys()]
    
    if form.is_valid():
        criteria = form.save(commit=False)
        criteria.rule = rule
        criteria.save()
        
        messages.success(request, "Dynamic criteria added successfully")
    else:
        messages.error(request, "Failed to add dynamic criteria")
    
    return redirect('notification_rule_detail', rule_id=rule.id)

@login_required
@permission_required('notifications.delete_subscriptionrule')
@require_POST
def notification_rule_delete_criteria(request, rule_id):
    """Delete a criteria from a rule"""
    rule = get_object_or_404(SubscriptionRule, id=rule_id)
    
    criteria_id = request.POST.get('criteria_id')
    criteria_type = request.POST.get('criteria_type')
    
    try:
        criteria_id = int(criteria_id)
        
        # Delete the criteria based on type
        if criteria_type == 'global':
            criteria = get_object_or_404(GlobalRoleCriteria, id=criteria_id, rule=rule)
            criteria.delete()
            messages.success(request, "Global role criteria deleted successfully")
        
        elif criteria_type == 'org':
            criteria = get_object_or_404(OrgUnitRoleCriteria, id=criteria_id, rule=rule)
            criteria.delete()
            messages.success(request, "Organizational unit role criteria deleted successfully")
        
        elif criteria_type == 'job':
            criteria = get_object_or_404(JobRoleCriteria, id=criteria_id, rule=rule)
            criteria.delete()
            messages.success(request, "Job role criteria deleted successfully")
        
        elif criteria_type == 'phase':
            criteria = get_object_or_404(PhaseRoleCriteria, id=criteria_id, rule=rule)
            criteria.delete()
            messages.success(request, "Phase role criteria deleted successfully")
        
        elif criteria_type == 'dynamic':
            criteria = get_object_or_404(DynamicRuleCriteria, id=criteria_id, rule=rule)
            criteria.delete()
            messages.success(request, "Dynamic criteria deleted successfully")
        
        else:
            messages.error(request, "Invalid criteria type")
    
    except (ValueError, TypeError):
        messages.error(request, "Invalid criteria ID")
    
    return redirect('notification_rule_detail', rule_id=rule.id)

@login_required
@permission_required('notifications.view_subscriptionrule')
def view_rule_subscriptions(request, rule_id):
    """View all subscriptions created by a rule"""
    rule = get_object_or_404(SubscriptionRule, id=rule_id)
    
    # Get subscriptions
    subscriptions = NotificationSubscription.objects.filter(
        notification_type=rule.notification_type,
        created_by_rule=True
    ).select_related('user').order_by('-created_at')
    
    # Paginate results
    paginator = Paginator(subscriptions, 20)
    page_number = request.GET.get('page')
    subscriptions = paginator.get_page(page_number)
    
    context = {
        'rule': rule,
        'subscriptions': subscriptions,
    }
    
    return render(request, 'notification_rules/subscriptions.html', context)


@permission_required('notifications.change_subscriptionrule')
def notification_rule_reapply(request, rule_id):
    """Re-apply a subscription rule to all relevant entities"""
    rule = get_object_or_404(SubscriptionRule, id=rule_id)
    
    if request.method == 'POST':
        # First, remove existing subscriptions created by this rule
        NotificationSubscription.objects.filter(
            created_by_rule=True,
            rule_id=rule.id
        ).delete()
        
        # Re-apply the rule
        from notifications.utils import apply_rule_to_all_entities
        apply_rule_to_all_entities(rule)
        
        messages.success(request, f"Rule '{rule.name}' has been re-applied to all relevant entities.")
        return redirect('notification_rule_detail', rule_id=rule_id)
    
    # Show confirmation page
    context = {
        'rule': rule,
    }
    return render(request, 'notification_rules/rule_reapply_confirm.html', context)