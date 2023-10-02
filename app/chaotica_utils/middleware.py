from django.http import HttpResponse, HttpResponseRedirect
from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import reverse, redirect
from .models import User
from django.urls import reverse
from django.conf import settings
from constance import config
import pprint

class HealthCheckMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.META['PATH_INFO'] == '/ping':
            return HttpResponse('pong!')


class NewInstallMiddleware(MiddlewareMixin):
    def process_request(self, request):
        new_install = User.objects.all().count() <= 1
        excludedURLs = [
            '/signup/',
            '/quote',
            '/static/',
        ]
        if new_install and not request.user.is_authenticated:
            if request.path not in excludedURLs:
                # Redirect to signup page...
                return HttpResponseRedirect(reverse('signup'))

class MaintenanceModeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.META.get('PATH_INFO', "")
        shouldRedirect = False

        if settings.MAINTENANCE_MODE:
            if not request.user.is_superuser:
                if path!=reverse("maintenance"):
                    shouldRedirect = True
        
        if shouldRedirect:
            response = redirect(reverse("maintenance"))
            return response
        else:
            response = self.get_response(request)
            return response