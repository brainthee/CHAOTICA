"""/api/v1/ serializers, one module per area."""

from .people import (  # noqa: F401
    UserSerializer,
    UserStatusUpdateSerializer,
    UserProfileUpdateSerializer,
    UserJobLevelUpdateSerializer,
    UserCostUpdateSerializer,
    OrganisationalUnitSerializer,
    OrganisationalUnitMemberSerializer,
    LeaveRequestSerializer,
    UserSkillSerializer,
    QualificationRecordSerializer,
)
from .clients import (  # noqa: F401
    ClientSerializer,
)
from .jobs import (  # noqa: F401
    JobSerializer,
    ProjectSerializer,
)
from .phases import (  # noqa: F401
    PhaseSerializer,
)
from .schedule import (  # noqa: F401
    TimeSlotTypeSerializer,
    TimeSlotSerializer,
    HolidaySerializer,
    ScheduleUserAvailabilitySerializer,
    ScheduleSerializer,
)
from .catalogue import (  # noqa: F401
    SkillCategorySerializer,
    SkillSerializer,
    QualificationSerializer,
    ServiceSerializer,
)
