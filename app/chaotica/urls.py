"""
URL configuration for chaotica project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include, re_path
from django.http import HttpResponseRedirect
from django.conf import settings
from django.conf.urls.static import static
from debug_toolbar.toolbar import debug_toolbar_urls

urlpatterns = [
    re_path(r"^$", lambda r: HttpResponseRedirect("dashboard/"), name="home"),
    re_path(r"^dashboard/", include("dashboard.urls")),
    path("admin/doc/", include("django.contrib.admindocs.urls")),
    path("auth/", include("django.contrib.auth.urls")),
    path("admin/", admin.site.urls),
    path('explorer/', include('explorer.urls')),
    path("oauth2/", include("django_auth_adfs.urls")),
    re_path(r"", include("chaotica_utils.urls")),
    re_path(r"", include("jobtracker.urls")),
    path("rm_sync/", include("rm_sync.urls")),
]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += debug_toolbar_urls()
