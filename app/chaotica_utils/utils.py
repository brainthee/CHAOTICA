from .models import User, Notification
from .enums import *
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.conf import settings as django_settings

def SendUserNotification(
        user: User, 
        notification_type: NotificationTypes, 
        title: str, message: str, 
        email_template: str, 
        icon: str=None,
        action_link: str=None,
        send_inapp: bool=True,
        send_email: bool=True,
        **kwargs) -> bool:
    # Lets see if we can do notifications
    ## In-app notification
    if send_inapp:
        Notification.objects.create(user=user, title=title, message=message, icon=icon, link=action_link)

    ## Email notification
    if send_email:
        kwargs['SITE_DOMAIN'] = django_settings.SITE_DOMAIN
        kwargs['SITE_PROTO'] = django_settings.SITE_PROTO
        msg_html = render_to_string(email_template, kwargs)
        send_mail(  
            title, message, None, [user.email], html_message=msg_html,
        )