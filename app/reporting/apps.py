from django.apps import AppConfig


class ReportingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'reporting'
    verbose_name = 'Reporting'

    def ready(self):
        # Import signals or any startup code here
        pass