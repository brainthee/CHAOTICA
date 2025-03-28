import json
from django.utils.crypto import get_random_string

# Define keys for session storage
SESSION_REPORT_WIZARD_KEY = 'report_wizard_data'
SESSION_REPORT_WIZARD_ID_KEY = 'report_wizard_id'

class SessionService:
    """
    Service for managing report wizard session data
    """
    
    @staticmethod
    def get_wizard_id(request):
        """
        Get or create a unique ID for the current wizard session
        """
        if SESSION_REPORT_WIZARD_ID_KEY not in request.session:
            request.session[SESSION_REPORT_WIZARD_ID_KEY] = get_random_string(32)
        return request.session[SESSION_REPORT_WIZARD_ID_KEY]
    
    @staticmethod
    def reset_wizard(request):
        """
        Reset the wizard session data
        """
        if SESSION_REPORT_WIZARD_KEY in request.session:
            del request.session[SESSION_REPORT_WIZARD_KEY]
        if SESSION_REPORT_WIZARD_ID_KEY in request.session:
            del request.session[SESSION_REPORT_WIZARD_ID_KEY]
        request.session.modified = True
    
    @staticmethod
    def save_wizard_data(request, data):
        """
        Save the wizard data to the session
        """
        request.session[SESSION_REPORT_WIZARD_KEY] = data
        request.session.modified = True
    
    @staticmethod
    def get_wizard_data(request):
        """
        Get the wizard data from the session
        """
        return request.session.get(SESSION_REPORT_WIZARD_KEY, {})
    
    @staticmethod
    def update_wizard_step(request, step_name, step_data):
        """
        Update a specific step in the wizard data
        """
        wizard_data = SessionService.get_wizard_data(request)
        wizard_data[step_name] = step_data
        SessionService.save_wizard_data(request, wizard_data)
    
    @staticmethod
    def get_wizard_step(request, step_name):
        """
        Get a specific step from the wizard data
        """
        wizard_data = SessionService.get_wizard_data(request)
        return wizard_data.get(step_name, {})
    
    @staticmethod
    def wizard_step_completed(request, step_name):
        """
        Check if a specific wizard step has been completed
        """
        wizard_data = SessionService.get_wizard_data(request)
        return step_name in wizard_data and wizard_data[step_name]
    
    @staticmethod
    def get_report_definition(request):
        """
        Get the complete report definition from the wizard data
        """
        wizard_data = SessionService.get_wizard_data(request)
        
        # Basic report data
        report_data = {
            'name': wizard_data.get('report_name', ''),
            'description': wizard_data.get('report_description', ''),
            'is_private': wizard_data.get('is_private', True),
        }
        
        # Data area
        data_area_step = wizard_data.get('data_area', {})
        if data_area_step:
            report_data['data_area_id'] = data_area_step.get('data_area_id')
            report_data['population_filter'] = data_area_step.get('population_filter')
        
        # Fields
        fields_step = wizard_data.get('fields', {})
        if fields_step:
            report_data['fields'] = fields_step.get('selected_fields', [])
        
        # Filters
        filters_step = wizard_data.get('filters', {})
        if filters_step:
            report_data['filters'] = filters_step.get('filter_conditions', [])
        
        # Sort order
        sorts_step = wizard_data.get('sorts', {})
        if sorts_step:
            report_data['sorts'] = sorts_step.get('sort_fields', [])
        
        # Presentation
        presentation_step = wizard_data.get('presentation', {})
        if presentation_step:
            report_data['presentation_type'] = presentation_step.get('presentation_type', 'excel')
            report_data['presentation_options'] = presentation_step.get('presentation_options', {})
            report_data['allow_presentation_choice'] = presentation_step.get('allow_presentation_choice', False)
        
        return report_data