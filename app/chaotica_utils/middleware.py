from django.http import HttpResponse, HttpResponseRedirect
from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import reverse, redirect
from .models import User
from django.urls import reverse
from django.conf import settings

class HealthCheckMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.META['PATH_INFO'] == '/ping':
            return HttpResponse('pong!')


class NewInstallMiddleware(MiddlewareMixin):
    def process_request(self, request):
        new_install = User.objects.all().count() <= 1
        excluded_urls = [
            '/signup/',
            '/quote',
            '/static/',
        ]
        if new_install and not request.user.is_authenticated:
            if request.path not in excluded_urls:
                # Redirect to signup page...
                return HttpResponseRedirect(reverse('signup'))

class MaintenanceModeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.META.get('PATH_INFO', "")
        should_redirect = False

        if settings.MAINTENANCE_MODE and not request.user.is_superuser and path!=reverse("maintenance"):
            should_redirect = True
        
        if should_redirect:
            response = redirect(reverse("maintenance"))
            return response
        else:
            response = self.get_response(request)
            return response