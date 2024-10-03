from django.urls import path, include, re_path
from . import views


urlpatterns = [
    path("settings", views.rm_settings, name="rm_settings"),
]