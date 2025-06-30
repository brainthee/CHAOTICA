from django.conf import settings 

def defaults(_):
    return {'SENTRY_FRONTEND_DSN': settings.SENTRY_FRONTEND_DSN}