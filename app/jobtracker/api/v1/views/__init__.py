"""/api/v1/ viewsets, one module per area (re-exported for urls.py)."""

from .people import (  # noqa: F401
    UserViewSet,
    OrganisationalUnitViewSet,
    LeaveRequestViewSet,
    UserSkillViewSet,
    QualificationRecordViewSet,
)
from .clients import (  # noqa: F401
    ClientViewSet,
)
from .jobs import (  # noqa: F401
    JobViewSet,
    ProjectViewSet,
)
from .phases import (  # noqa: F401
    PhaseViewSet,
)
from .schedule import (  # noqa: F401
    TimeSlotTypeViewSet,
    TimeSlotViewSet,
    TimeSlotCommentViewSet,
    ScheduleViewSet,
)
from .catalogue import (  # noqa: F401
    SkillCategoryViewSet,
    SkillViewSet,
    QualificationViewSet,
    ServiceViewSet,
)
