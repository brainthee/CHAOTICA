from django.urls import reverse_lazy
from ..mixins import PrefetchRelatedMixin
from ..enums import GlobalRoles
from qsessions.models import Session
from .common import ChaoticaBaseGlobalRoleView
from django.views.generic.list import ListView
from django.utils import timezone
from django.db.models import Q
import json
from datetime import datetime
from ..models import User, IPTag, IPCIDRRange
import ipaddress



class SessionBaseView(ChaoticaBaseGlobalRoleView):
    model = Session
    fields = "__all__"
    success_url = reverse_lazy("session_list")
    template_name = 'session_list.html'
    context_object_name = 'sessions'

    role_required = GlobalRoles.ADMIN

    def get_context_data(self, **kwargs):
        context = super(SessionBaseView, self).get_context_data(**kwargs)
        return context

    def get_queryset(self):
        queryset = Session.objects.all()
        return queryset


class SessionListView(PrefetchRelatedMixin, SessionBaseView, ListView):
    prefetch_related = ["groups", "unit_memberships", "unit_memberships__unit"]
    """View to list all jobs.
    Use the 'job_list' variable in the template
    to access all job objects"""

    
    def get_ip_tag(self, ip_address):
        """
        Get the IP tag for a given IP address by checking against CIDR ranges.
        Returns the first matching tag or None.
        """
        if not ip_address:
            return None
        
        try:
            ip_obj = ipaddress.ip_address(ip_address)
        except ValueError:
            return None
        
        # Get all active CIDR ranges
        cidr_ranges = IPCIDRRange.objects.filter(
            is_active=True,
            tag__is_active=True
        ).select_related('tag')
        
        for cidr_range in cidr_ranges:
            try:
                network = cidr_range.get_network()
                if ip_obj in network:
                    return cidr_range.tag
            except ValueError:
                # Skip invalid CIDR ranges
                continue
        
        return None
    
    def get_queryset(self):
        """
        Get all active (non-expired) sessions, ordered by most recent activity.
        """
        queryset = Session.objects.filter(
            expire_date__gt=timezone.now()
        ).order_by('-expire_date')
        
        return queryset
    
    def get_context_data(self, **kwargs):
        """
        Add additional context for the template.
        """
        context = super(SessionListView, self).get_context_data(**kwargs)
        
        # Add summary statistics
        all_sessions = Session.objects.all()
        context['total_sessions'] = all_sessions.count()
        context['active_sessions'] = Session.objects.filter(
            expire_date__gt=timezone.now()
        ).count()
        context['expired_sessions'] = Session.objects.filter(
            expire_date__lte=timezone.now()
        ).count()
        

        context['current_time'] = timezone.now()
        
        # Add IP tags to sessions
        sessions_with_tags = []
        for session in context['sessions']:
            session.ip_tag = self.get_ip_tag(session.ip)
            sessions_with_tags.append(session)
        
        context['sessions'] = sessions_with_tags
        
        return context