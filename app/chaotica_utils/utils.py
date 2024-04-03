from .models import User, Notification
from .enums import NotificationTypes
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.conf import settings as django_settings
from datetime import timedelta
from uuid import UUID
import re
from datetime import datetime
from .enums import GlobalRoles
from django.utils.text import slugify
from menu import MenuItem
from django.conf import settings


def unique_slug_generator(instance, value=None):
    """Creates a unique slug

    Args:
        instance (_type_): _description_
        value (_type_, optional): _description_. Defaults to None.

    Returns:
        _type_: _description_
    """
    slug = slugify(value)
    new_slug = slug
    Klass = instance.__class__
    numb = 1
    while Klass.objects.filter(slug=new_slug).exists():
        new_slug = "{slug}-{num}".format(
            slug=slug,
            num=numb
        )
        numb += 1
    return new_slug


class RoleMenuItem(MenuItem):
    """Custom MenuItem that checks permissions based on the view associated
    with a URL"""
    def check(self, request):
        if self.requiredRole and request.user.is_authenticated:
            if self.requiredRole == "*":
                self.visible = request.user.groups.filter().exists()
            else:
                self.visible = request.user.groups.filter(
                    name=settings.GLOBAL_GROUP_PREFIX+GlobalRoles.CHOICES[self.requiredRole][1]).exists()
        else:
            self.visible = False


class PermMenuItem(MenuItem):
    """Custom MenuItem that checks permissions based on the view associated
    with a URL"""
    def check(self, request):
        if self.perm and request.user.is_authenticated:
             self.visible = request.user.has_perm(self.perm)
        else:
            self.visible = False


def fullcalendar_to_datetime(date):
    # 2023-10-23T00:00:00+01:00
    # 2023-10-23T00:00:00+01:00
    # 2023-10-30T00:00:00Z
    # 2023-10-30T00:00:00Z
    datetime_pattern = re.compile(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})')
    dt_format = '%Y-%m-%dT%H:%M:%S'
    return datetime.strptime(datetime_pattern.search(date).group(), dt_format)


def is_valid_uuid(uuid_to_test, version=4):
    """
    Check if uuid_to_test is a valid UUID.
    
     Parameters
    ----------
    uuid_to_test : str
    version : {1, 2, 3, 4}
    
     Returns
    -------
    `True` if uuid_to_test is a valid UUID, otherwise `False`.
    
     Examples
    --------
    >>> is_valid_uuid('c9bf9e57-1685-4c89-bafb-ff5af830be8a')
    True
    >>> is_valid_uuid('c9bf9e58')
    False
    """
    
    try:
        uuid_obj = UUID(uuid_to_test, version=version)
    except ValueError:
        return False
    return str(uuid_obj) == uuid_to_test


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
        if action_link:
            # Check if it needs to be made external
            if not action_link.startswith('{}://{}'.format(
                django_settings.SITE_PROTO,
                django_settings.SITE_DOMAIN)):
                self.action_link = ext_reverse(action_link)
            else:
                self.action_link = action_link
        else:
            self.action_link = None
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