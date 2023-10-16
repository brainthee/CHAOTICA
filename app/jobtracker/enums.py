class AddressTypes():
    BILLING, REGISTERED = range(0, 2)
    # make sure to add new items at end to not corrupt database!
    CHOICES = (
        (BILLING, 'Billing address'),
        (REGISTERED, 'Registered address'),
    )

class LinkType():
    LN_OTHER = 0
    LN_GITLABISSUE = 1
    LN_SHAREPOINT = 2
    LN_TEAMS = 3
    LN_SCHED = 4
    LN_HOSTING = 5
    CHOICES = (
        (LN_OTHER, 'Other'),
        (LN_GITLABISSUE, 'GitLab Issue'),
        (LN_SHAREPOINT, 'SharePoint'),
        (LN_TEAMS, 'Teams'),
        (LN_SCHED, 'Scheduling'),
        (LN_HOSTING, 'Hosting'),
    )

class FeedbackType():
    SCOPE = 0
    TECH = 1
    PRES = 2
    OTHER = 3
    CHOICES = (
        (SCOPE, 'Scoping'),
        (TECH, 'Technical'),
        (PRES, 'Presentation'),
        (OTHER, 'Other'),
    )

class TimeSlotType():
    GENERIC = 0
    INTERNAL = 1
    DELIVERY = 2
    LEAVE = 3
    CHOICES = (
        (GENERIC, 'Generic'), # Blank slot effectively
        (INTERNAL, 'Internal'),
        (DELIVERY, 'Delivery'),
        (LEAVE, 'Leave'),
    )

class TimeSlotDeliveryRole():
    NA = 0
    DELIVERY = 1
    REPORTING = 2
    MANAGEMENT = 3
    QA = 4
    OVERSIGHT = 5
    DEBRIEF = 6
    CONTINGENCY = 7
    OTHER = 8
    CHOICES = (
        (NA, 'None'),
        (DELIVERY, 'Delivery'),
        (REPORTING, 'Reporting'),
        (MANAGEMENT, 'Management'),
        (QA, 'QA'),
        (OVERSIGHT, 'Oversight'),
        (DEBRIEF, 'Debrief'),
        (CONTINGENCY, 'Contingency'),
        (OTHER, 'Other'),
    )
    REQUIRED_ALLOCATIONS = (DELIVERY, QA)


class JobStatuses():
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
        (DRAFT, "Draft"), # Initial state
        (PENDING_SCOPE, "Pending Scoping"), # Manual
        (SCOPING, "Scoping"), # Manual
        (SCOPING_ADDITIONAL_INFO_REQUIRED, "Additional Scoping Required"), # Manual
        (PENDING_SCOPING_SIGNOFF, "Pending Scope Signoff"), # Manual
        (SCOPING_COMPLETE, "Scoping Complete"), # Manual
        (PENDING_START, "Pending Start"), # Automatic - when phases are scheduled and confirmed!
        (IN_PROGRESS, "In Progress"), # Automatic - when any phase starts
        (COMPLETED, "Completed"), # Automatic - when ALL phases end
        (LOST, "Lost"), # Manual - only available before IN_PROGRESS
        (DELETED, "Deleted"), # Manual - Always available - Won't show up in search or lists. Only admin
        (ARCHIVED, "Archived"), # Automatic - after X days after COMPLTED - Will show up in search but not lists
    )
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

class PhaseStatuses():
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
        (DRAFT, "Draft"), # Initial State
        (PENDING_SCHED, "Pending Scheduling"), # Automatic - when job moved to SCOPING_COMPLETE
        (SCHEDULED_TENTATIVE, "Schedule Tentative"), # Automatic - when phases are scheduled
        (SCHEDULED_CONFIRMED, "Schedule Confirmed"), # Manual - when everyone accepts scheduled phases
        (PRE_CHECKS, "Pre-checks"), # Automatic - 1 week before start date
        (CLIENT_NOT_READY, "Client Not Ready"), # Manual - by consultant if not ready
        (READY_TO_BEGIN, "Ready to Begin"), # Manual - by consultant if ready
        (IN_PROGRESS, "In Progress"), # Automatic - on starting day
        (PENDING_TQA, "Pending Technical QA"), # Manual - when testing is finished
        (QA_TECH, "Tech QA"), # Manual - when report finished
        (QA_TECH_AUTHOR_UPDATES, "Author Tech Updates"), # Manual
        (PENDING_PQA, "Pending Presentation QA"), # Manual - when TQA is finished
        (QA_PRES, "Pres QA"), # Manual
        (QA_PRES_AUTHOR_UPDATES, "Author Pres Updates"), # Manual
        (COMPLETED, "Completed"), # Manual - when report done
        (DELIVERED, "Delivered"), # Manual - when report delivered
        (CANCELLED, "Cancelled"),
        (POSTPONED, "Postponed"),
        (DELETED, "Deleted"), # Manual - Always available - Won't show up in search or lists. Only admin
        (ARCHIVED, "Archived"), # Automatic - after X days after COMPLETED - Will show up in search but not lists
    )
    BS_COLOURS = (
        (DRAFT, "secondary"),
        (PENDING_SCHED, "secondary"),
        (SCHEDULED_TENTATIVE, "secondary"),
        (SCHEDULED_CONFIRMED, "secondary"),
        (PRE_CHECKS, "secondary"),
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


class JobRelation():
    LINKED = 0
    PREVIOUS_JOB = 1

    CHOICES = (
        (LINKED, "Linked"),
        (PREVIOUS_JOB, "Previous Job"),
    )


class RestrictedClassifications():
    UNKNOWN = 0
    OFFICIAL = 1
    OFFICIAL_SENSITIVE = 2
    SECRET = 3
    # make sure to add new items at end to not corrupt database!
    CHOICES = (
        (SECRET, 'SECRET'),
        (OFFICIAL_SENSITIVE, 'OFFICIAL-SENSITIVE'),
        (OFFICIAL, 'OFFICIAL'),
        (UNKNOWN, 'Unknown'),
    )


BOOL_CHOICES = ((None, ''), (True, 'Yes'), (False, 'No'))


class TechQARatings():
    MAJOR_CHANGES_NEEDED, SIGNIFICANT_CHANGES_NEEDED, AVERAGE, GOOD, EXCELLENT = range(0, 5)
    # make sure to add new items at end to not corrupt database!
    CHOICES = (
        (MAJOR_CHANGES_NEEDED, 'Major changes needed to much of the report'),
        (SIGNIFICANT_CHANGES_NEEDED, 'Significant changes needed (e.g. add/remove findings, re-write execute summary)'),
        (AVERAGE, 'Average report. Some changes needed to finding detail or executive summary'),
        (GOOD, 'Good. Minor changes (punctuation, grammar, or minor details only)'),
        (EXCELLENT, 'Excellent. No/trivial changes required'),
    )


class PresQARatings():
    MAJOR_CHANGES_NEEDED, SIGNIFICANT_CHANGES_NEEDED, AVERAGE, GOOD, EXCELLENT = range(0, 5)
    # make sure to add new items at end to not corrupt database!
    CHOICES = (
        (MAJOR_CHANGES_NEEDED, 'Major changes needed to much of the report'),
        (SIGNIFICANT_CHANGES_NEEDED, 'Significant changes needed (client specific requirements missing, '
                                     'issues to be restructured, headers and footers to be updated, etc.)'),
        (AVERAGE, 'Average report. Some changes neeeded to text or structure of report which required clarification '
                  'from author/Tech QA\'er'),
        (GOOD, 'Good. Minor changes (punctuation, grammar, or minor details only)'),
        (EXCELLENT, 'Excellent. No/trivial changes required'),
    )


class UserSkillRatings():
    NO_EXPERIENCE = 0
    CAN_DO_WITH_SUPPORT = 1
    CAN_DO_ALONE = 2
    SPECIALIST = 3
    CHOICES = (
        (NO_EXPERIENCE, 'No experience'),
        (CAN_DO_WITH_SUPPORT, 'Can do with support'),
        (CAN_DO_ALONE, 'Can do alone'),
        (SPECIALIST, 'Specialist'),
    )