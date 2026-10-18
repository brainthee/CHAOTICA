"""URL routing for the versioned /api/v1/ API.

Mounted at ``/api/v1/`` from the project root URLconf. Kept entirely separate
from the legacy ``jobtracker/urls.py`` ``/api/`` DataTables feeds.
"""

from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework import routers

from . import views
from .views import dashboard, platform
from .auth import ThrottledObtainAuthToken

app_name = "api_v1"

router = routers.DefaultRouter()
router.register(r"users", views.UserViewSet, basename="user")
router.register(r"org-units", views.OrganisationalUnitViewSet, basename="org-unit")
router.register(r"clients", views.ClientViewSet, basename="client")
router.register(r"contacts", views.ContactViewSet, basename="contact")
router.register(r"frameworks", views.FrameworkViewSet, basename="framework")
router.register(r"jobs", views.JobViewSet, basename="job")
router.register(r"phases", views.PhaseViewSet, basename="phase")
router.register(r"projects", views.ProjectViewSet, basename="project")
router.register(r"timeslots", views.TimeSlotViewSet, basename="timeslot")
router.register(r"schedule", views.ScheduleViewSet, basename="schedule")
router.register(
    r"timeslot-comments", views.TimeSlotCommentViewSet, basename="timeslot-comment"
)
router.register(r"timeslot-types", views.TimeSlotTypeViewSet, basename="timeslot-type")
router.register(r"leave-requests", views.LeaveRequestViewSet, basename="leave-request")
router.register(r"skills", views.SkillViewSet, basename="skill")
router.register(
    r"skill-categories", views.SkillCategoryViewSet, basename="skill-category"
)
router.register(r"user-skills", views.UserSkillViewSet, basename="user-skill")
router.register(r"qualifications", views.QualificationViewSet, basename="qualification")
router.register(
    r"qualification-records",
    views.QualificationRecordViewSet,
    basename="qualification-record",
)
router.register(r"services", views.ServiceViewSet, basename="service")
router.register(r"awarding-bodies", views.AwardingBodyViewSet, basename="awarding-body")

urlpatterns = [
    path("meta/", platform.MetaView.as_view(), name="meta"),
    path("me/", platform.MeView.as_view(), name="me"),
    path(
        "me/preferences/", platform.MePreferencesView.as_view(), name="me-preferences"
    ),
    path("me/schedule/", platform.MeScheduleView.as_view(), name="me-schedule"),
    path("me/dashboard/", dashboard.MeDashboardView.as_view(), name="me-dashboard"),
    path("me/alarms/", dashboard.MeAlarmsView.as_view(), name="me-alarms"),
    path("entropy/", dashboard.EntropyView.as_view(), name="entropy"),
    path(
        "notifications/",
        dashboard.NotificationListView.as_view(),
        name="notifications",
    ),
    path(
        "notifications/unread-count/",
        dashboard.NotificationUnreadCountView.as_view(),
        name="notifications-unread-count",
    ),
    path(
        "notifications/mark-read/",
        dashboard.NotificationMarkReadView.as_view(),
        name="notifications-mark-read",
    ),
    path(
        "notifications/mark-all-read/",
        dashboard.NotificationMarkAllReadView.as_view(),
        name="notifications-mark-all-read",
    ),
    path(
        "realtime/ticket/",
        platform.RealtimeTicketView.as_view(),
        name="realtime-ticket",
    ),
    path("search/", platform.SearchView.as_view(), name="search"),
    path("search/goto/", platform.SearchGotoView.as_view(), name="search-goto"),
    path("", include(router.urls)),
    # Token issuance for programmatic clients (POST username/password -> token).
    path("auth/token/", ThrottledObtainAuthToken.as_view(), name="token"),
    # OpenAPI schema + interactive docs.
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="api_v1:schema"),
        name="swagger-ui",
    ),
    path(
        "schema/redoc/",
        SpectacularRedocView.as_view(url_name="api_v1:schema"),
        name="redoc",
    ),
]
