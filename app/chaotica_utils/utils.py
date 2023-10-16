from .models import User, Notification
from .enums import NotificationTypes
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.conf import settings as django_settings
from datetime import timedelta


def ext_reverse(reversed_url):
    return '{}://{}{}'.format(
        django_settings.SITE_PROTO,
        django_settings.SITE_DOMAIN,
        reversed_url)

def last_day_of_month(any_day):
    # The day 28 exists in every month. 4 days later, it's always next month
    next_month = any_day.replace(day=28) + timedelta(days=4)
    # subtracting the number of the current day brings us back one month
    return next_month - timedelta(days=next_month.day)

class AppNotification:
    """
    This feels wrong...?
    """

    def __init__(self,
        notification_type: NotificationTypes, 
        title: str, message: str, 
        email_template: str, 
        icon: str=None,
        action_link: str=None,
        send_inapp: bool=True,
        send_email: bool=True,
        **kwargs):

        self.type = notification_type
        self.title = title
        self.message = message
        self.email_template = email_template
        self.icon = icon
        self.action_link = action_link
        self.send_inapp = send_inapp
        self.send_email = send_email
        self.context = {}
        self.context.update(kwargs)

    def send_to_user(
            self,
            user: User, ) -> bool:
        # Lets see if we can do notifications
        ## In-app notification
        if self.send_inapp:
            Notification.objects.create(user=user, title=self.title, 
                                        message=self.message, 
                                        icon=self.icon, link=self.action_link)

        ## Email notification
        if self.send_email:
            self.context['SITE_DOMAIN'] = django_settings.SITE_DOMAIN
            self.context['SITE_PROTO'] = django_settings.SITE_PROTO
            self.context['title'] = self.title
            self.context['message'] = self.message
            self.context['icon'] = self.icon
            self.context['action_link'] = self.action_link
            self.context['user'] = user
            msg_html = render_to_string(self.email_template, self.context)
            send_mail(  
                self.title, self.message, None, [user.email], html_message=msg_html,
            )