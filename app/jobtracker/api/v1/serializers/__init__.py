"""/api/v1/ serializers, one module per area."""

from .platform import (  # noqa: F401
    MetaAuthSerializer,
    MetaBrandingSerializer,
    MetaSerializer,
    MembershipSerializer,
    MeSerializer,
    PreferencesSerializer,
    SearchGroupSerializer,
    SearchResultsSerializer,
)
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
    ContactCardSerializer,
    LinkSerializer,
    BillingBadgeSerializer,
    WorkflowStepSerializer,
    WorkflowTransitionSerializer,
    WorkflowSerializer,
    WorkflowCapabilitiesMixin,
    JobDetailSerializer,
    TeamRoleSerializer,
    TeamPhaseRowSerializer,
    TeamMemberSerializer,
    JobTeamMemberSerializer,
    EffortSerializer,
    SalesMemberSerializer,
    JobSalesSerializer,
    NoteSerializer,
    ActivitySerializer,
    SupportRoleSerializer,
)
from .phases import (  # noqa: F401
    PhaseSerializer,
    PhaseDetailSerializer,
    FeedbackItemSerializer,
    PhaseFeedbackSerializer,
)
from .schedule import (  # noqa: F401
    TimeSlotTypeSerializer,
    ScheduleTimeSlotSerializer,
    TimeSlotSerializer,
    ScheduleLeaveSerializer,
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
