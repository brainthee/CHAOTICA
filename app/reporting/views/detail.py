import logging
from django.contrib import messages
from django.views.generic import DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.translation import gettext_lazy as _

from ..models import Report
from ..engine import ReportEngine
from ..formatters import get_formatter

logger = logging.getLogger(__name__)


class ReportDetailView(LoginRequiredMixin, DetailView):
    """View to display report details"""
    model = Report
    template_name = 'reporting/report_detail.html'
    context_object_name = 'report'
    
    def get_queryset(self):
        """Ensure user can access the report"""
        return Report.objects.filter(
            created_by=self.request.user
        ) | Report.objects.filter(
            is_private=False
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add schedules if the user is the owner
        if self.object.created_by == self.request.user:
            context['schedules'] = self.object.schedules.all()
            
        # Add recent outputs for this report
        context['recent_outputs'] = self.object.outputs.all().order_by('-created_at')[:5]
        
        return context


class ReportRunView(LoginRequiredMixin, DetailView):
    """View for running a report"""
    model = Report
    template_name = 'reporting/report_run.html'
    context_object_name = 'report'
    
    def get_queryset(self):
        """Ensure user can access the report"""
        return Report.objects.filter(
            created_by=self.request.user
        ) | Report.objects.filter(
            is_private=False
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get filter prompts if any
        filter_prompts = self._get_filter_prompts()
        context['filter_prompts'] = filter_prompts
        context['has_prompts'] = len(filter_prompts) > 0
        
        # Only add presentation choices if allowed
        if self.object.allow_runtime_presentation_choice:
            context['presentation_choices'] = [
                ('excel', _('Excel Spreadsheet')),
                ('html', _('Web Page (HTML)')),
                ('pdf', _('PDF Document')),
                ('word', _('Word Document')),
                ('csv', _('CSV File')),
                ('json', _('JSON File')),
            ]
        
        return context
    
    def _get_filter_prompts(self):
        """Extract filter prompts from report definition"""
        prompts = []
        
        for filter_group in self.object.filter_conditions:
            for condition in filter_group.get('conditions', []):
                if condition.get('prompt'):
                    prompt_id = condition.get('prompt_id', f"prompt_{len(prompts)}")
                    field = condition.get('field', '')
                    operator = condition.get('operator', '')
                    
                    # Get field type to determine appropriate input type
                    field_type = self._get_field_type(field)
                    
                    prompts.append({
                        'id': prompt_id,
                        'prompt': condition.get('prompt'),
                        'field': field,
                        'operator': operator,
                        'field_type': field_type
                    })
        
        return prompts
    
    def _get_field_type(self, field_name):
        """Determine field type for a given field name"""
        # This is a simplified version - a real implementation would
        # examine the actual model fields
        if 'date' in field_name.lower():
            return 'date'
        elif 'time' in field_name.lower():
            return 'datetime'
        elif field_name in ['is_active', 'is_staff', 'is_superuser']:
            return 'boolean'
        elif field_name in ['id', 'status', 'count']:
            return 'number'
        else:
            return 'text'
    
    def post(self, request, *args, **kwargs):
        """Handle report execution request"""
        self.object = self.get_object()
        
        # Get runtime parameters
        params = {}
        
        # Extract filter prompt values
        for key, value in request.POST.items():
            if key.startswith('prompt_'):
                params[key] = value
        
        # Get requested format
        format_type = request.POST.get('format', self.object.default_presentation)
        
        try:
            # Execute the report
            report_engine = ReportEngine(self.object, request.user)
            report_data = report_engine.execute(params)
            
            # Format the report
            formatter = get_formatter(format_type, self.object, report_data)
            
            # Save the output if it's not HTML (which is displayed in browser)
            if format_type != 'html':
                self._save_report_output(formatter, format_type)
            
            # Return the appropriate response based on format
            return formatter.get_http_response()
                
        except Exception as e:
            # Log the error
            logger.error(f"Error running report {self.object.id}: {str(e)}", exc_info=True)
            
            # Show error message
            messages.error(request, _('Error running report: {0}').format(str(e)))
            
            # Redirect back to the run page
            return self.get(request, *args, **kwargs)
    
    def _save_report_output(self, formatter, format_type):
        """Save the report output for later reference"""
        from ..models import SavedReportOutput
        
        try:
            # Create the output record
            output = SavedReportOutput(
                report=self.object,
                created_by=self.request.user,
                format=format_type,
            )
            
            # Save the file
            output_file = formatter.get_file()
            file_size = output_file.getbuffer().nbytes if hasattr(output_file, 'getbuffer') else 0
            
            filename = f"{formatter.filename}.{format_type}"
            if format_type == 'excel':
                filename = f"{formatter.filename}.xlsx"
            elif format_type == 'word':
                filename = f"{formatter.filename}.docx"
                
            output.file.save(filename, output_file)
            output.file_size = file_size
            output.save()
            
        except Exception as e:
            logger.error(f"Error saving report output: {e}", exc_info=True)
            # Continue without saving output - we don't want to block the report generation