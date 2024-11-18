class LinkType:
    LN_OTHER = 0
    LN_GITLABISSUE = 1
    LN_SHAREPOINT = 2
    LN_TEAMS = 3
    LN_SCHED = 4
    LN_HOSTING = 5
    CHOICES = (
        (LN_OTHER, "Other"),
        (LN_GITLABISSUE, "GitLab Issue"),
        (LN_SHAREPOINT, "SharePoint"),
        (LN_TEAMS, "Teams"),
        (LN_SCHED, "Scheduling"),
        (LN_HOSTING, "Hosting"),
    )


class FeedbackType:
    SCOPE = 0
    TECH = 1
    PRES = 2
    OTHER = 3
    CHOICES = (
        (SCOPE, "Scoping"),
        (TECH, "Technical"),
        (PRES, "Presentation"),
        (OTHER, "Other"),
    )


class AvailabilityType:
    UNAVAILABLE = 0
    AVAILABLE = 1
    BUSY_INTERNAL = 2
    BUSY_DELIVERY = 3
    CHOICES = (
        (UNAVAILABLE, "Unavailable"),  # Person isn't available for anything. E.g. leave
        (AVAILABLE, "Available"),  # Available for anything (e.g. unassigned)
        (BUSY_INTERNAL, "Busy - Internal"),  # Busy on internal work
        (BUSY_DELIVERY, "Busy - Delivery"),  # Busy on client work
    )


class DefaultTimeSlotTypes:
    BANK_HOL = 1
    LEAVE = 2
    SICK = 3
    SELF_LEARNING = 4
    TRAINING = 5
    TRAINING_DELIVER = 6
    UNASSIGNED = 7
    DELIVERY = 8
    CATCHUP = 9
    CONFERENCE = 10
    INTERNAL_PROJECT = 11
    SERVICE_DEVELOPMENT = 12
    INTERVIEW = 13
    DEFAULTS = [
        {
            "pk": BANK_HOL,
            "name": "Bank Holiday",
            "built_in": True,
            "is_delivery": False,
            "is_assignable": False,
            "is_working": False,
            "availability": AvailabilityType.UNAVAILABLE,
        },
        {
            "pk": LEAVE,
            "name": "Annual Leave",
            "built_in": True,
            "is_delivery": False,
            "is_assignable": False,
            "is_working": False,
            "availability": AvailabilityType.UNAVAILABLE,
        },
        {
            "pk": SICK,
            "name": "Sick",
            "built_in": True,
            "is_delivery": False,
            "is_assignable": True,
            "is_working": False,
            "availability": AvailabilityType.UNAVAILABLE,
        },
        {
            "pk": SELF_LEARNING,
            "name": "Self-led Learning",
            "built_in": True,
            "is_delivery": False,
            "is_assignable": True,
            "is_working": True,
            "availability": AvailabilityType.BUSY_INTERNAL,
        },
        {
            "pk": TRAINING,
            "name": "Training",
            "built_in": True,
            "is_delivery": False,
            "is_assignable": True,
            "is_working": True,
            "availability": AvailabilityType.BUSY_INTERNAL,
        },
        {
            "pk": TRAINING_DELIVER,
            "name": "Training - Deliver",
            "built_in": True,
            "is_delivery": False,
            "is_assignable": True,
            "is_working": True,
            "availability": AvailabilityType.BUSY_INTERNAL,
        },
        {
            "pk": UNASSIGNED,
            "name": "Unassigned",
            "built_in": True,
            "is_delivery": False,
            "is_assignable": False,
            "is_working": True,
            "availability": AvailabilityType.AVAILABLE,
        },
        {
            "pk": DELIVERY,
            "name": "Delivery",
            "built_in": True,
            "is_delivery": True,
            "is_assignable": False,  # No - this should be used only when booking through a phase
            "is_working": True,
            "availability": AvailabilityType.BUSY_DELIVERY,
        },
        {
            "pk": CATCHUP,
            "name": "Catchup",
            "built_in": True,
            "is_delivery": False,
            "is_assignable": True,
            "is_working": True,
            "availability": AvailabilityType.BUSY_INTERNAL,
        },
        {
            "pk": CONFERENCE,
            "name": "Conference",
            "built_in": True,
            "is_delivery": False,
            "is_assignable": True,
            "is_working": True,
            "availability": AvailabilityType.BUSY_INTERNAL,
        },
        {
            "pk": INTERNAL_PROJECT,
            "name": "Internal Project",
            "built_in": True,
            "is_delivery": False,
            "is_assignable": False, # No - this should be used only when booking through a phase
            "is_working": True,
            "availability": AvailabilityType.BUSY_INTERNAL,
        },
        {
            "pk": SERVICE_DEVELOPMENT,
            "name": "Service Development",
            "built_in": True,
            "is_delivery": False,
            "is_assignable": True,
            "is_working": True,
            "availability": AvailabilityType.BUSY_INTERNAL,
        },
        {
            "pk": INTERVIEW,
            "name": "Interview",
            "built_in": True,
            "is_delivery": False,
            "is_assignable": True,
            "is_working": True,
            "availability": AvailabilityType.BUSY_INTERNAL,
        },
    ]


class TimeSlotDeliveryRole:
    NA = 0
    DELIVERY = 1
    REPORTING = 2
    MANAGEMENT = 3
    QA = 4
    OVERSIGHT = 5
    DEBRIEF = 6
    CONTINGENCY = 7
    SHADOW = 8
    OTHER = 8
    CHOICES = (
        (NA, "None"),
        (DELIVERY, "Delivery"),
        (REPORTING, "Reporting"),
        (MANAGEMENT, "Management"),
        (QA, "QA"),
        (OVERSIGHT, "Oversight"),
        (DEBRIEF, "Debrief"),
        (CONTINGENCY, "Contingency"),
        (SHADOW, "Shadowing"),
        (OTHER, "Other"),
    )
    REQUIRED_ALLOCATIONS = (DELIVERY, QA)

class JobGuestPermissions:
    ALLOWED = [
        "jobtracker.view_job_schedule",
        "jobtracker.can_update_job",
        "jobtracker.can_add_note_job",
        "jobtracker.can_view_jobs",
        "jobtracker.view_job_schedule",
    ]

class JobSupportRole:
    OTHER = 0
    COMMERCIAL = 1
    QA = 1
    SCOPE = 2
    CHOICES = (
        (OTHER, "Other"),
        (COMMERCIAL, "Commercial"),
        (QA, "QA"),
        (SCOPE, "Scope"),
    )


class ProjectStatuses:
    UNTRACKED = 0
    PENDING = 1
    IN_PROGRESS = 2
    COMPLETE = 3

    CHOICES = (
        (UNTRACKED, "Untracked"),
        (PENDING, "Pending"),
        (IN_PROGRESS, "In Progress"),
        (COMPLETE, "Complete"),
    )

    BS_COLOURS = (
        (UNTRACKED, "secondary"),
        (PENDING, "info"),
        (IN_PROGRESS, "warning"),
        (COMPLETE, "success"),
    )


class JobStatuses:
    DRAFT = 0
    PENDING_SCOPE = 1
    SCOPING = 2
    SCOPING_ADDITIONAL_INFO_REQUIRED = 3
    PENDING_SCOPING_SIGNOFF = 4
    SCOPING_COMPLETE = 5
    PENDING_START = 6
    IN_PROGRESS = 7
    COMPLETED = 8
    LOST = 9
    DELETED = 10
    ARCHIVED = 11

    CHOICES = (
        (DRAFT, "Draft"),  # Initial state
        (PENDING_SCOPE, "Pending Scoping"),  # Manual
        (SCOPING, "Scoping"),  # Manual
        (SCOPING_ADDITIONAL_INFO_REQUIRED, "Additional Scoping Required"),  # Manual
        (PENDING_SCOPING_SIGNOFF, "Pending Scope Signoff"),  # Manual
        (SCOPING_COMPLETE, "Scoping Complete"),  # Manual
        (
            PENDING_START,
            "Pending Start",
        ),  # Automatic - when phases are scheduled and confirmed!
        (IN_PROGRESS, "In Progress"),  # Automatic - when any phase starts
        (COMPLETED, "Completed"),  # Automatic - when ALL phases end
        (LOST, "Lost"),  # Manual - only available before IN_PROGRESS
        (
            DELETED,
            "Deleted",
        ),  # Manual - Always available - Won't show up in search or lists. Only admin
        (
            ARCHIVED,
            "Archived",
        ),  # Automatic - after X days after COMPLTED - Will show up in search but not lists
    )

    CHANGEABLE_FIELDS = (
        (
            DRAFT,
            [
                "unit",
                "client",
                "indicative_services",
                "title",
                "external_id",
                "revenue",
                "overview",
                "account_manager",
                "dep_account_manager",
                "desired_start_date",
                "desired_delivery_date",
            ],
        ),
        (
            PENDING_SCOPE,
            [
                "unit",
                "client",
                "indicative_services",
                "title",
                "external_id",
                "revenue",
                "overview",
                "account_manager",
                "dep_account_manager",
                "desired_start_date",
                "desired_delivery_date",
            ],
        ),
        (
            SCOPING,
            [
                "unit",
                "client",
                "indicative_services",
                "title",
                "external_id",
                "revenue",
                "overview",
                "account_manager",
                "dep_account_manager",
                "desired_start_date",
                "desired_delivery_date",
            ],
        ),
        (
            SCOPING_ADDITIONAL_INFO_REQUIRED,
            [
                "unit",
                "client",
                "indicative_services",
                "title",
                "external_id",
                "revenue",
                "overview",
                "account_manager",
                "dep_account_manager",
                "desired_start_date",
                "desired_delivery_date",
            ],
        ),
        (
            PENDING_SCOPING_SIGNOFF,
            [
                "unit",
                "client",
                "indicative_services",
                "title",
                "external_id",
                "revenue",
                "overview",
                "account_manager",
                "dep_account_manager",
                "desired_start_date",
                "desired_delivery_date",
            ],
        ),
        (
            SCOPING_COMPLETE,
            [
                "unit",
                "client",
                "indicative_services",
                "title",
                "external_id",
                "revenue",
                "overview",
                "account_manager",
                "dep_account_manager",
                "desired_start_date",
                "desired_delivery_date",
            ],
        ),
        (
            PENDING_START,
            [
                "unit",
                "client",
                "indicative_services",
                "title",
                "external_id",
                "revenue",
                "overview",
                "account_manager",
                "dep_account_manager",
                "desired_start_date",
                "desired_delivery_date",
            ],
        ),
        (
            IN_PROGRESS,
            [
                "unit",
                "client",
                "indicative_services",
                "title",
                "external_id",
                "revenue",
                "overview",
                "account_manager",
                "dep_account_manager",
                "desired_start_date",
                "desired_delivery_date",
            ],
        ),
        (COMPLETED, []),
        (LOST, []),
        (DELETED, []),
        (ARCHIVED, []),
    )

    ACTIVE_STATUSES = [
        DRAFT,
        PENDING_SCOPE,
        SCOPING,
        SCOPING_ADDITIONAL_INFO_REQUIRED,
        PENDING_SCOPING_SIGNOFF,
        SCOPING_COMPLETE,
        PENDING_START,
        IN_PROGRESS,
    ]

    BS_COLOURS = (
        (DRAFT, "secondary"),
        (PENDING_SCOPE, "info"),
        (SCOPING, "info"),
        (SCOPING_ADDITIONAL_INFO_REQUIRED, "info"),
        (PENDING_SCOPING_SIGNOFF, "warning"),
        (SCOPING_COMPLETE, "success"),
        (PENDING_START, "success"),
        (IN_PROGRESS, "danger"),
        (COMPLETED, "success"),
        (LOST, "secondary"),
        (DELETED, "secondary"),
        (ARCHIVED, "secondary"),
    )


class PhaseStatuses:
    DRAFT = 0
    PENDING_SCHED = 1
    SCHEDULED_TENTATIVE = 2
    SCHEDULED_CONFIRMED = 3
    PRE_CHECKS = 4
    CLIENT_NOT_READY = 5
    READY_TO_BEGIN = 6
    IN_PROGRESS = 7
    PENDING_TQA = 8
    QA_TECH = 9
    QA_TECH_AUTHOR_UPDATES = 10
    PENDING_PQA = 11
    QA_PRES = 12
    QA_PRES_AUTHOR_UPDATES = 13
    COMPLETED = 14
    DELIVERED = 15
    CANCELLED = 16
    POSTPONED = 17
    DELETED = 18
    ARCHIVED = 19

    CHOICES = (
        (DRAFT, "Draft"),  # Initial State
        (
            PENDING_SCHED,
            "Pending Scheduling",
        ),  # Automatic - when job moved to SCOPING_COMPLETE
        (
            SCHEDULED_TENTATIVE,
            "Schedule Tentative",
        ),  # Automatic - when phases are scheduled
        (
            SCHEDULED_CONFIRMED,
            "Schedule Confirmed",
        ),  # Manual - when everyone accepts scheduled phases
        (PRE_CHECKS, "Pre-checks"),  # Automatic - 1 week before start date
        (CLIENT_NOT_READY, "Client Not Ready"),  # Manual - by consultant if not ready
        (READY_TO_BEGIN, "Ready to Begin"),  # Manual - by consultant if ready
        (IN_PROGRESS, "In Progress"),  # Automatic - on starting day
        (PENDING_TQA, "Pending Technical QA"),  # Manual - when testing is finished
        (QA_TECH, "Tech QA"),  # Manual - when report finished
        (QA_TECH_AUTHOR_UPDATES, "Author Tech Updates"),  # Manual
        (PENDING_PQA, "Pending Presentation QA"),  # Manual - when TQA is finished
        (QA_PRES, "Pres QA"),  # Manual
        (QA_PRES_AUTHOR_UPDATES, "Author Pres Updates"),  # Manual
        (COMPLETED, "Completed"),  # Manual - when report done
        (DELIVERED, "Delivered"),  # Manual - when report delivered
        (CANCELLED, "Cancelled"),
        (POSTPONED, "Postponed"),
        (
            DELETED,
            "Deleted",
        ),  # Manual - Always available - Won't show up in search or lists. Only admin
        (
            ARCHIVED,
            "Archived",
        ),  # Automatic - after X days after COMPLETED - Will show up in search but not lists
    )

    CHANGEABLE_FIELDS = (
        (
            DRAFT,
            [
                "phase_number",
                "title",
                "service",
                "description",
                "test_target",
                "comm_reqs",
                "delivery_hours",
                "reporting_hours",
                "mgmt_hours",
                "qa_hours",
                "oversight_hours",
                "debrief_hours",
                "contingency_hours",
                "other_hours",
                "desired_start_date",
                "due_to_techqa_set",
                "due_to_presqa_set",
                "desired_delivery_date",
                "is_testing_onsite",
                "is_reporting_onsite",
                "number_of_reports",
                "report_to_be_left_on_client_site",
                "location",
                "restrictions",
                "scheduling_requirements",
                "prerequisites",
            ],
        ),
        (
            PENDING_SCHED,
            [
                "phase_number",
                "title",
                "service",
                "description",
                "test_target",
                "comm_reqs",
                "delivery_hours",
                "reporting_hours",
                "mgmt_hours",
                "qa_hours",
                "oversight_hours",
                "debrief_hours",
                "contingency_hours",
                "other_hours",
                "desired_start_date",
                "due_to_techqa_set",
                "due_to_presqa_set",
                "desired_delivery_date",
                "is_testing_onsite",
                "is_reporting_onsite",
                "number_of_reports",
                "report_to_be_left_on_client_site",
                "location",
                "restrictions",
                "scheduling_requirements",
                "prerequisites",
            ],
        ),
        (
            SCHEDULED_TENTATIVE,
            [
                "phase_number",
                "title",
                "service",
                "description",
                "test_target",
                "comm_reqs",
                "delivery_hours",
                "reporting_hours",
                "mgmt_hours",
                "qa_hours",
                "oversight_hours",
                "debrief_hours",
                "contingency_hours",
                "other_hours",
                "desired_start_date",
                "due_to_techqa_set",
                "due_to_presqa_set",
                "desired_delivery_date",
                "is_testing_onsite",
                "is_reporting_onsite",
                "number_of_reports",
                "report_to_be_left_on_client_site",
                "location",
                "restrictions",
                "scheduling_requirements",
                "prerequisites",
            ],
        ),
        (
            SCHEDULED_CONFIRMED,
            [
                "phase_number",
                "title",
                "service",
                "description",
                "test_target",
                "comm_reqs",
                "delivery_hours",
                "reporting_hours",
                "mgmt_hours",
                "qa_hours",
                "oversight_hours",
                "debrief_hours",
                "contingency_hours",
                "other_hours",
                "desired_start_date",
                "due_to_techqa_set",
                "due_to_presqa_set",
                "desired_delivery_date",
                "is_testing_onsite",
                "is_reporting_onsite",
                "number_of_reports",
                "report_to_be_left_on_client_site",
                "location",
                "restrictions",
                "scheduling_requirements",
                "prerequisites",
            ],
        ),
        (
            PRE_CHECKS,
            [
                "phase_number",
                "title",
                "service",
                "description",
                "test_target",
                "comm_reqs",
                "delivery_hours",
                "reporting_hours",
                "mgmt_hours",
                "qa_hours",
                "oversight_hours",
                "debrief_hours",
                "contingency_hours",
                "other_hours",
                "desired_start_date",
                "due_to_techqa_set",
                "due_to_presqa_set",
                "desired_delivery_date",
                "is_testing_onsite",
                "is_reporting_onsite",
                "number_of_reports",
                "report_to_be_left_on_client_site",
                "location",
                "restrictions",
                "scheduling_requirements",
                "prerequisites",
            ],
        ),
        (
            CLIENT_NOT_READY,
            [
                "phase_number",
                "title",
                "service",
                "description",
                "test_target",
                "comm_reqs",
                "delivery_hours",
                "reporting_hours",
                "mgmt_hours",
                "qa_hours",
                "oversight_hours",
                "debrief_hours",
                "contingency_hours",
                "other_hours",
                "desired_start_date",
                "due_to_techqa_set",
                "due_to_presqa_set",
                "desired_delivery_date",
                "is_testing_onsite",
                "is_reporting_onsite",
                "number_of_reports",
                "report_to_be_left_on_client_site",
                "location",
                "restrictions",
                "scheduling_requirements",
                "prerequisites",
            ],
        ),
        (
            READY_TO_BEGIN,
            [
                "phase_number",
                "title",
                "service",
                "description",
                "test_target",
                "comm_reqs",
                "delivery_hours",
                "reporting_hours",
                "mgmt_hours",
                "qa_hours",
                "oversight_hours",
                "debrief_hours",
                "contingency_hours",
                "other_hours",
                "desired_start_date",
                "due_to_techqa_set",
                "due_to_presqa_set",
                "desired_delivery_date",
                "is_testing_onsite",
                "is_reporting_onsite",
                "number_of_reports",
                "report_to_be_left_on_client_site",
                "location",
                "restrictions",
                "scheduling_requirements",
                "prerequisites",
            ],
        ),
        (
            IN_PROGRESS,
            [
                "phase_number",
                "title",
                "service",
                "description",
                "test_target",
                "comm_reqs",
                "delivery_hours",
                "reporting_hours",
                "mgmt_hours",
                "qa_hours",
                "oversight_hours",
                "debrief_hours",
                "contingency_hours",
                "other_hours",
                "desired_start_date",
                "due_to_techqa_set",
                "due_to_presqa_set",
                "desired_delivery_date",
                "is_testing_onsite",
                "is_reporting_onsite",
                "number_of_reports",
                "report_to_be_left_on_client_site",
                "location",
                "restrictions",
                "scheduling_requirements",
                "prerequisites",
            ],
        ),
        (PENDING_TQA, []),
        (QA_TECH, []),
        (QA_TECH_AUTHOR_UPDATES, []),
        (PENDING_PQA, []),
        (QA_PRES, []),
        (QA_PRES_AUTHOR_UPDATES, []),
        (COMPLETED, []),
        (DELIVERED, []),
        (CANCELLED, []),
        (POSTPONED, []),
        (DELETED, []),
        (ARCHIVED, []),
    )

    ACTIVE_STATUSES = [
        DRAFT,
        PENDING_SCHED,
        SCHEDULED_TENTATIVE,
        SCHEDULED_CONFIRMED,
        PRE_CHECKS,
        CLIENT_NOT_READY,
        READY_TO_BEGIN,
        IN_PROGRESS,
        PENDING_TQA,
        QA_TECH,
        QA_TECH_AUTHOR_UPDATES,
        PENDING_PQA,
        QA_PRES,
        QA_PRES_AUTHOR_UPDATES,
        COMPLETED,
        DELIVERED,
    ]

    BS_COLOURS = (
        (DRAFT, "secondary"),
        (PENDING_SCHED, "secondary"),
        (SCHEDULED_TENTATIVE, "warning"),
        (SCHEDULED_CONFIRMED, "success"),
        (PRE_CHECKS, "primary"),
        (CLIENT_NOT_READY, "warning"),
        (READY_TO_BEGIN, "success"),
        (IN_PROGRESS, "danger"),
        (PENDING_TQA, "secondary"),
        (QA_TECH, "info"),
        (QA_TECH_AUTHOR_UPDATES, "info"),
        (PENDING_PQA, "secondary"),
        (QA_PRES, "info"),
        (QA_PRES_AUTHOR_UPDATES, "info"),
        (COMPLETED, "success"),
        (DELIVERED, "success"),
        (CANCELLED, "secondary"),
        (POSTPONED, "secondary"),
        (DELETED, "secondary"),
        (ARCHIVED, "secondary"),
    )


class JobRelation:
    LINKED = 0
    PREVIOUS_JOB = 1

    CHOICES = (
        (LINKED, "Linked"),
        (PREVIOUS_JOB, "Previous Job"),
    )


class RestrictedClassifications:
    UNKNOWN = 0
    OFFICIAL = 1
    OFFICIAL_SENSITIVE = 2
    SECRET = 3
    # make sure to add new items at end to not corrupt database!
    CHOICES = (
        (SECRET, "SECRET"),
        (OFFICIAL_SENSITIVE, "OFFICIAL-SENSITIVE"),
        (OFFICIAL, "OFFICIAL"),
        (UNKNOWN, "Unknown"),
    )


BOOL_CHOICES = ((None, ""), (True, "Yes"), (False, "No"))


class TechQARatings:
    MAJOR_CHANGES_NEEDED, SIGNIFICANT_CHANGES_NEEDED, AVERAGE, GOOD, EXCELLENT = range(
        0, 5
    )
    # make sure to add new items at end to not corrupt database!
    CHOICES = (
        (MAJOR_CHANGES_NEEDED, "Major changes needed to much of the report"),
        (
            SIGNIFICANT_CHANGES_NEEDED,
            "Significant changes needed (e.g. add/remove findings, re-write execute summary)",
        ),
        (
            AVERAGE,
            "Average report. Some changes needed to finding detail or executive summary",
        ),
        (GOOD, "Good. Minor changes (punctuation, grammar, or minor details only)"),
        (EXCELLENT, "Excellent. No/trivial changes required"),
    )


class PresQARatings:
    MAJOR_CHANGES_NEEDED, SIGNIFICANT_CHANGES_NEEDED, AVERAGE, GOOD, EXCELLENT = range(
        0, 5
    )
    # make sure to add new items at end to not corrupt database!
    CHOICES = (
        (MAJOR_CHANGES_NEEDED, "Major changes needed to much of the report"),
        (
            SIGNIFICANT_CHANGES_NEEDED,
            "Significant changes needed (client specific requirements missing, "
            "issues to be restructured, headers and footers to be updated, etc.)",
        ),
        (
            AVERAGE,
            "Average report. Some changes neeeded to text or structure of report which required clarification "
            "from author/Tech QA'er",
        ),
        (GOOD, "Good. Minor changes (punctuation, grammar, or minor details only)"),
        (EXCELLENT, "Excellent. No/trivial changes required"),
    )


class UserSkillRatings:
    NO_EXPERIENCE = 0
    CAN_DO_WITH_SUPPORT = 1
    CAN_DO_ALONE = 2
    SPECIALIST = 3
    CHOICES = (
        (NO_EXPERIENCE, "No experience"),
        (CAN_DO_WITH_SUPPORT, "Require Support"),
        (CAN_DO_ALONE, "Independent"),
        (SPECIALIST, "Specialist"),
    )


class QualificationStatus:
    UNKNOWN = 0
    REVOKED = 1
    SUSPENDED = 2
    IN_PROGRESS = 3
    PENDING = 4
    ATTEMPTED = 5
    AWARDED = 6
    UNSUCCESSFUL = 7
    LAPSED = 8

    CHOICES = (
        (UNKNOWN, "Unknown"),
        (REVOKED, "Revoked"),
        (SUSPENDED, "Suspended"),
        (IN_PROGRESS, "In Progress"),
        (PENDING, "Pending"),
        (ATTEMPTED, "Attempted"),
        (AWARDED, "Awarded"),
        (UNSUCCESSFUL, "Unsuccessful"),
        (LAPSED, "Lapsed"),
    )

    BS_COLOURS = (
        (UNKNOWN, "secondary"),
        (REVOKED, "danger"),
        (SUSPENDED, "danger"),
        (IN_PROGRESS, "primary"),
        (PENDING, "primary"),
        (ATTEMPTED, "warning"),
        (AWARDED, "success"),
        (UNSUCCESSFUL, "danger"),
        (LAPSED, "secondary"),
    )
