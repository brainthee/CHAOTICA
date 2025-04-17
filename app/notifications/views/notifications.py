from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods, require_POST, require_GET
from django.core.paginator import Paginator

from notifications.models import Notification, NotificationSubscription, NotificationOptOut
from notifications.enums import NotificationTypes

import json
import logging

from django.template import loader
from django.http import (
    JsonResponse,
    HttpResponse,
)
import json
from chaotica_utils.views.common import page_defaults
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import get_object_or_404
from django.views.decorators.http import (
    require_http_methods,
)

logger = logging.getLogger(__name__)

@login_required
def notification_settings(request):
    from notifications.models import NotificationSubscription, NotificationCategory
    from notifications.enums import NotificationTypes
    
    # Handle form submission
    if request.method == 'POST':
        # Process notification preferences update
        for key, value in request.POST.items():
            if key.startswith('notification_'):
                # Parse the form field name
                parts = key.split('_')
                if len(parts) >= 3:
                    notification_type = int(parts[1])
                    setting_type = parts[2]  # 'email' or 'app'
                    
                    # Check if this is an entity-specific subscription
                    entity_type = None
                    entity_id = None
                    if len(parts) >= 5 and parts[3] == 'entity':
                        entity_type = parts[4]
                        entity_id = int(parts[5])
                    
                    # Find or create subscription
                    subscription, created = NotificationSubscription.objects.get_or_create(
                        user=request.user,
                        notification_type=notification_type,
                        entity_type=entity_type,
                        entity_id=entity_id,
                    )
                    
                    # Update settings
                    if setting_type == 'email':
                        subscription.email_enabled = value == 'on'
                    elif setting_type == 'app':
                        subscription.in_app_enabled = value == 'on'
                    
                    subscription.save()
        
        messages.success(request, "Notification settings updated successfully")
        return redirect('notification_settings')
    
    # Prepare notification types by category
    notification_types_by_category = {}
    for notification_type, label in NotificationTypes.CHOICES:
        category = NotificationTypes.CATEGORIES.get(notification_type, "Other")
        if category not in notification_types_by_category:
            notification_types_by_category[category] = []
        notification_types_by_category[category].append({
            'id': notification_type,
            'label': label
        })
    
    # Get user's current subscriptions
    subscriptions = NotificationSubscription.objects.filter(user=request.user)
    
    # Convert subscriptions to a more usable format
    user_preferences = {}
    for sub in subscriptions:
        # Use string keys to ensure template lookup works correctly
        key = str(sub.notification_type)
        if sub.entity_type and sub.entity_id:
            key = f"{sub.notification_type}_{sub.entity_type}_{sub.entity_id}"
        
        user_preferences[key] = {
            'email': sub.email_enabled,
            'app': sub.in_app_enabled
        }
    
    # Get entity-specific subscriptions (like followed jobs/phases)
    entity_subscriptions = subscriptions.exclude(entity_id__isnull=True).order_by('entity_type', 'entity_id')
    
    context = {
        'notification_types_by_category': notification_types_by_category,
        'user_preferences': user_preferences,
        'entity_subscriptions': entity_subscriptions,
    }
    
    template = loader.get_template("notification_settings.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@login_required
@require_http_methods(["GET", "POST"])
def notifications_api(request):
    """API endpoint for getting and marking notifications"""
    if request.method == "GET":
        # Get user's notifications, paginated
        page = request.GET.get('page', 1)
        per_page = request.GET.get('per_page', 10)
        unread_only = request.GET.get('unread_only') == 'true'
        
        notifications = Notification.objects.filter(user=request.user)
        if unread_only:
            notifications = notifications.filter(read=False)
            
        paginator = Paginator(notifications.order_by('-timestamp'), per_page)
        page_obj = paginator.get_page(page)
        
        data = {
            'count': paginator.count,
            'num_pages': paginator.num_pages,
            'current_page': int(page),
            'notifications': [
                {
                    'id': n.id,
                    'type': n.notification_type,
                    'type_display': n.get_notification_type_display(),
                    'timestamp': n.timestamp.isoformat(),
                    'title': n.title,
                    'message': n.message,
                    'link': n.link,
                    'read': n.read,
                    'entity_type': n.entity_type,
                    'entity_id': n.entity_id,
                    'metadata': n.metadata,
                }
                for n in page_obj.object_list
            ],
            'unread_count': Notification.objects.filter(user=request.user, read=False).count()
        }
        
        return JsonResponse(data)
    
    elif request.method == "POST":
        # Mark notifications as read/unread
        try:
            data = json.loads(request.body)
            notification_ids = data.get('notification_ids', [])
            action = data.get('action')
            
            if not notification_ids or action not in ['mark_read', 'mark_unread']:
                return JsonResponse({'error': 'Invalid parameters'}, status=400)
            
            # Only allow modifying user's own notifications
            notifications = Notification.objects.filter(id__in=notification_ids, user=request.user)
            
            if action == 'mark_read':
                notifications.update(read=True)
            elif action == 'mark_unread':
                notifications.update(read=False)
                
            return JsonResponse({'status': 'success', 'updated_count': notifications.count()})
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)


@login_required
@require_POST
def mark_all_read(request):
    """Mark all notifications as read for the current user"""
    count = Notification.objects.filter(user=request.user, read=False).update(read=True)
    return JsonResponse({'status': 'success', 'updated_count': count})


@login_required
@require_http_methods(["POST"])
def remove_notification_subscription(request):
    subscription_id = request.GET.get('subscription_id')
    
    if not subscription_id or not isinstance(subscription_id, int):
        return JsonResponse({'error': 'Invalid subscription_id'}, status=400)
    
    """Remove a specific notification subscription"""
    subscription = get_object_or_404(
        NotificationSubscription, 
        id=subscription_id, 
        user=request.user
    )
    subscription.delete()
    return JsonResponse({'status': 'success'})


@login_required
@require_POST
def follow_entity(request):
    from jobtracker.models import Job, Phase, OrganisationalUnit
    """Follow a specific entity (Job, Phase, etc.) for notifications"""
    try:
        data = json.loads(request.body)
        entity_type = data.get('entity_type')
        entity_id = data.get('entity_id')
        notification_types = data.get('notification_types', [])
        
        if not entity_type or not entity_id:
            return JsonResponse({'error': 'Missing entity_type or entity_id'}, status=400)
            
        # Validate entity exists
        entity = None
        if entity_type == 'Job':
            entity = get_object_or_404(Job, id=entity_id)
        elif entity_type == 'Phase':
            entity = get_object_or_404(Phase, id=entity_id)
        elif entity_type == 'OrganisationalUnit':
            entity = get_object_or_404(OrganisationalUnit, id=entity_id)
        else:
            return JsonResponse({'error': 'Invalid entity type'}, status=400)
            
        # If no specific notification types provided, use defaults for that entity type
        if not notification_types:
            if entity_type == 'Job':
                notification_types = [
                    NotificationTypes.JOB_STATUS_CHANGE,
                    NotificationTypes.JOB_CREATED
                ]
            elif entity_type == 'Phase':
                notification_types = [
                    NotificationTypes.PHASE_STATUS_CHANGE,
                    NotificationTypes.PHASE_LATE_TO_TQA,
                    NotificationTypes.PHASE_LATE_TO_PQA,
                    NotificationTypes.PHASE_LATE_TO_DELIVERY
                ]
            elif entity_type == 'OrganisationalUnit':
                notification_types = [
                    NotificationTypes.ORG_UNIT_ADDITION
                ]
                
        # Create subscriptions
        created_count = 0
        for notification_type in notification_types:
            subscription, created = NotificationSubscription.objects.get_or_create(
                user=request.user,
                notification_type=notification_type,
                entity_type=entity_type,
                entity_id=entity_id,
                defaults={
                    'email_enabled': True,
                    'in_app_enabled': True
                }
            )
            NotificationOptOut.objects.filter(
                user=request.user,
                notification_type=request.POST.get('notification_type'),
                entity_type=request.POST.get('entity_type'),
                entity_id=request.POST.get('entity_id')
            ).delete()
            if created:
                created_count += 1
                
        return JsonResponse({
            'status': 'success', 
            'created_count': created_count,
            'message': f"Now following {entity_type} #{entity_id}"
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)


@login_required
@require_POST
def unfollow_entity(request):
    """Unfollow a specific entity (Job, Phase, etc.)"""
    data = {}
    
    # Get the subscription details from the request
    subscription_id = request.POST.get('subscription_id')

    if subscription_id:
        try:
            # Find the subscription
            subscription = NotificationSubscription.objects.get(
                id=subscription_id, 
                user=request.user
            )
            
            # Store the details before deleting
            notification_type = subscription.notification_type
            entity_type = subscription.entity_type
            entity_id = subscription.entity_id
            
            # Delete the subscription
            subscription.delete()
            
            # Create an opt-out record to prevent auto-resubscription
            NotificationOptOut.objects.get_or_create(
                user=request.user,
                notification_type=notification_type,
                entity_type=entity_type,
                entity_id=entity_id
            )
            
            data['status'] = 'success'
            
        except NotificationSubscription.DoesNotExist:
            data['status'] = 'error'
            data['message'] = 'Subscription not found'
    else:
        # Alternative approach if you're using separate parameters
        # notification_type = request.POST.get('notification_type')
        entity_type = request.POST.get('entity_type')
        entity_id = request.POST.get('entity_id')
        
        if entity_type and entity_id:
            try:
                # notification_type = int(notification_type)
                entity_id = int(entity_id)
                
                # Delete the subscription
                deleted, _ = NotificationSubscription.objects.filter(
                    user=request.user,
                    # notification_type=notification_type,
                    entity_type=entity_type,
                    entity_id=entity_id
                ).delete()
                
                if deleted > 0:
                    # Create an opt-out record
                    NotificationOptOut.objects.get_or_create(
                        user=request.user,
                        # notification_type=notification_type,
                        entity_type=entity_type,
                        entity_id=entity_id
                    )
                    data['status'] = 'success'
                else:
                    data['status'] = 'error'
                    data['message'] = 'No subscription found to delete'
            except (ValueError, TypeError):
                data['status'] = 'error'
                data['message'] = 'Invalid parameters'
        else:
            data['status'] = 'error'
            data['message'] = 'Missing required parameters'
    
    return JsonResponse(data)

    try:
        data = json.loads(request.body)
        entity_type = data.get('entity_type')
        entity_id = data.get('entity_id')
        
        if not entity_type or not entity_id:
            return JsonResponse({'error': 'Missing entity_type or entity_id'}, status=400)
            
        # Delete all subscriptions for this entity
        deleted_count = NotificationSubscription.objects.filter(
            user=request.user,
            entity_type=entity_type,
            entity_id=entity_id
        ).delete()[0]

        NotificationOptOut.objects.get_or_create(
            user=request.user,
            notification_type=notification_type,
            entity_type=entity_type,
            entity_id=entity_id
        )
        
        return JsonResponse({
            'status': 'success', 
            'deleted_count': deleted_count,
            'message': f"No longer following {entity_type} #{entity_id}"
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)


@login_required
@require_GET
def get_user_subscriptions(request):
    """Get all notification subscriptions for the current user"""
    # Get all user subscriptions
    subscriptions = NotificationSubscription.objects.filter(user=request.user)
    
    # Format data
    global_subscriptions = []
    entity_subscriptions = []
    
    for sub in subscriptions:
        subscription_data = {
            'id': sub.id,
            'notification_type': sub.notification_type,
            'email_enabled': sub.email_enabled,
            'in_app_enabled': sub.in_app_enabled,
        }
        
        if sub.entity_type and sub.entity_id:
            subscription_data['entity_type'] = sub.entity_type
            subscription_data['entity_id'] = sub.entity_id
            entity_subscriptions.append(subscription_data)
        else:
            global_subscriptions.append(subscription_data)
    
    return JsonResponse({
        'global_subscriptions': global_subscriptions,
        'entity_subscriptions': entity_subscriptions
    })


@login_required
@require_GET
def notification_subscription_status(request):
    """Check if user is following a specific entity"""
    entity_type = request.GET.get('entity_type')
    entity_id = request.GET.get('entity_id')
    
    if not entity_type or not entity_id:
        return JsonResponse({'error': 'Missing entity_type or entity_id'}, status=400)
        
    # Check if any subscriptions exist for this entity
    is_following = NotificationSubscription.objects.filter(
        user=request.user,
        entity_type=entity_type,
        entity_id=entity_id
    ).exists()
    
    subscriptions = []
    if is_following:
        subscriptions = list(NotificationSubscription.objects.filter(
            user=request.user,
            entity_type=entity_type,
            entity_id=entity_id
        ).values('id', 'notification_type', 'email_enabled', 'in_app_enabled'))
    
    return JsonResponse({
        'is_following': is_following,
        'subscriptions': subscriptions,
    })


@login_required
@require_GET
def get_unread_count(request):
    """Get the count of unread notifications"""
    count = Notification.objects.filter(user=request.user, read=False).count()
    return JsonResponse({'unread_count': count})


@login_required
@require_POST
def update_subscription_settings(request):
    """Update email/app enabled settings for a subscription"""
    subscription_id = request.GET.get('subscription_id')
    
    if not subscription_id or not isinstance(subscription_id, int):
        return JsonResponse({'error': 'Invalid subscription_id'}, status=400)
    
    try:
        data = json.loads(request.body)
        email_enabled = data.get('email_enabled')
        in_app_enabled = data.get('in_app_enabled')
        
        subscription = get_object_or_404(
            NotificationSubscription, 
            id=subscription_id, 
            user=request.user
        )
        
        if email_enabled is not None:
            subscription.email_enabled = email_enabled
        if in_app_enabled is not None:
            subscription.in_app_enabled = in_app_enabled
            
        subscription.save()
        
        return JsonResponse({
            'status': 'success',
            'subscription': {
                'id': subscription.id,
                'notification_type': subscription.notification_type,
                'entity_type': subscription.entity_type,
                'entity_id': subscription.entity_id,
                'email_enabled': subscription.email_enabled,
                'in_app_enabled': subscription.in_app_enabled,
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)


@login_required
@require_GET
def get_notification_types(request):
    """Get all available notification types"""
    notification_types = [
        {
            'id': nt_id,
            'name': nt_name,
            'category': NotificationTypes.CATEGORIES.get(nt_id, "Other"),
        }
        for nt_id, nt_name in NotificationTypes.CHOICES
    ]
    
    # Group by category
    categories = {}
    for nt in notification_types:
        category = nt['category']
        if category not in categories:
            categories[category] = []
        categories[category].append(nt)
    
    return JsonResponse({
        'notification_types': notification_types,
        'categories': categories,
    })