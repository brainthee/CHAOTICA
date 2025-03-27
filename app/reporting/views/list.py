from django.db.models import Q
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin

from ..models import Report, ReportCategory


class ReportListView(LoginRequiredMixin, ListView):
    """View to list available reports"""
    model = Report
    template_name = 'reporting/report_list.html'
    context_object_name = 'reports'
    
    def get_queryset(self):
        """Get reports the user can access"""
        # Show reports created by the user or public reports
        queryset = Report.objects.filter(
            Q(created_by=self.request.user) |
            Q(is_private=False)
        ).distinct()
        
        # Filter by category if specified
        category_id = self.request.GET.get('category')
        if category_id and category_id.isdigit():
            queryset = queryset.filter(category_id=int(category_id))
            
        # Filter by search term if provided
        search_term = self.request.GET.get('search')
        if search_term:
            queryset = queryset.filter(
                Q(name__icontains=search_term) |
                Q(description__icontains=search_term)
            )
            
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = ReportCategory.objects.all()
        
        # Include the currently active category if any
        category_id = self.request.GET.get('category')
        if category_id and category_id.isdigit():
            try:
                context['active_category'] = ReportCategory.objects.get(id=int(category_id))
            except ReportCategory.DoesNotExist:
                pass
                
        # Include recent outputs for this user
        context['recent_outputs'] = self.request.user.report_outputs.all().order_by('-created_at')[:10]
        
        return context