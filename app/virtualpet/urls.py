# virtualpet/urls.py

from django.urls import path
from . import views
from . import api

app_name = 'virtualpet'

urlpatterns = [
    # Views
    path('settings/', views.pet_settings, name='settings'),
    path('toggle/', views.toggle_pet, name='toggle'),
    
    # # API Endpoints
    path('api/pet/sync/', api.sync_pet_data, name='api_sync_pet'),
    path('api/pet/team/', api.get_team_pets, name='api_team_pets'),
    path('api/pet/toggle/', api.toggle_pet, name='api_toggle_pet'),
    path('api/pet/record-pentest/', api.record_pentest_completion, name='api_record_pentest'),
]