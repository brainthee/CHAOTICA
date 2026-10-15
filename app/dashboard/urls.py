from django.urls import path
from . import views


urlpatterns = [
    path("", views.index, name="dashboard"),
    path("tab/<str:key>/", views.dashboard_tab, name="dashboard_tab"),
    path("team/", views.team_tab, name="dashboard_team_tab"),
    path("team-leave/", views.team_leave_tab, name="dashboard_team_leave_tab"),
]
