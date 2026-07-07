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
from rest_framework.authtoken.views import obtain_auth_token

from . import views

app_name = "api_v1"

router = routers.DefaultRouter()
router.register(r"users", views.UserViewSet, basename="user")
router.register(r"org-units", views.OrganisationalUnitViewSet, basename="org-unit")
router.register(r"clients", views.ClientViewSet, basename="client")
router.register(r"jobs", views.JobViewSet, basename="job")
router.register(r"phases", views.PhaseViewSet, basename="phase")
router.register(r"projects", views.ProjectViewSet, basename="project")
router.register(r"timeslots", views.TimeSlotViewSet, basename="timeslot")
router.register(
    r"timeslot-types", views.TimeSlotTypeViewSet, basename="timeslot-type"
)
router.register(
    r"leave-requests", views.LeaveRequestViewSet, basename="leave-request"
)
router.register(r"skills", views.SkillViewSet, basename="skill")
router.register(
    r"skill-categories", views.SkillCategoryViewSet, basename="skill-category"
)
router.register(r"user-skills", views.UserSkillViewSet, basename="user-skill")
router.register(
    r"qualifications", views.QualificationViewSet, basename="qualification"
)
router.register(
    r"qualification-records",
    views.QualificationRecordViewSet,
    basename="qualification-record",
)
router.register(r"services", views.ServiceViewSet, basename="service")

urlpatterns = [
    path("", include(router.urls)),
    # Token issuance for programmatic clients (POST username/password -> token).
    path("auth/token/", obtain_auth_token, name="token"),
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
