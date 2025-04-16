class NotificationTypes:
    SYSTEM = 0

    JOB_CREATED = 10
    JOB_STATUS_CHANGE = 11
    JOB_PENDING_SCOPING = 12
    JOB_PENDING_SCOPE_SIGNOFF = 13
    JOB_SCOPING_COMPLETE = 14
    JOB_COMPLETE = 29
    
    PHASE_CREATED = 30
    PHASE_STATUS_CHANGE = 31
    PHASE_LATE_TO_TQA = 32
    PHASE_LATE_TO_PQA = 33
    PHASE_LATE_TO_DELIVERY = 34
    PHASE_NEW_NOTE = 35
    PHASE_TQA_UPDATES = 36
    PHASE_PQA_UPDATES = 37
    PHASE_FEEDBACK = 38
    PHASE_PENDING_SCHED = 39
    PHASE_SCHEDULED_CONFIRMED = 40
    PHASE_READY_PRECHECKS = 41
    PHASE_CLIENT_NOT_READY = 42
    PHASE_READY = 43
    PHASE_IN_PROGRESS = 44
    PHASE_PENDING_TQA = 45
    PHASE_PENDING_PQA = 46
    PHASE_PENDING_DELIVERY = 47
    PHASE_COMPLETED = 48
    PHASE_POSTPONED = 49
    PHASE_PRECHECKS_OVERDUE = 50


    # Leave notifications
    LEAVE_SUBMITTED = 60
    LEAVE_APPROVED = 61
    LEAVE_REJECTED = 62
    LEAVE_CANCELLED = 63
    
    CLIENT_ONBOARDING_RENEWAL = 70
    
    CHOICES = (
        (SYSTEM, "System Notification"),

        (JOB_CREATED, "Job Created"),
        (JOB_STATUS_CHANGE, "Job Status Change"),
        (JOB_PENDING_SCOPING, "Job Pending Scoping"),
        (JOB_PENDING_SCOPE_SIGNOFF, "Job Pending Scope Signoff"),
        (JOB_SCOPING_COMPLETE, "Job Scoping Complete"),
        (JOB_COMPLETE, "Job Complete"),
        
        (PHASE_STATUS_CHANGE, "Phase Status Change"),
        (PHASE_LATE_TO_TQA, "Phase Late to TQA"),
        (PHASE_LATE_TO_PQA, "Phase Late to PQA"),
        (PHASE_TQA_UPDATES, "Phase TQA Updates"),
        (PHASE_PQA_UPDATES, "Phase PQA Updates"),
        (PHASE_LATE_TO_DELIVERY, "Phase Late to Delivery"),
        (PHASE_NEW_NOTE, "Phase Note Added"),
        (PHASE_FEEDBACK, "Phase Feedback"),
        (PHASE_PENDING_SCHED, "Phase Pending Scheduling"),
        (PHASE_SCHEDULED_CONFIRMED, "Phase Scheduling Confirmed"),
        (PHASE_READY_PRECHECKS, "Phase Ready for Pre-checks"),
        (PHASE_CLIENT_NOT_READY, "Phase Client Not Ready"),
        (PHASE_READY, "Phase Ready to Begin"),
        (PHASE_IN_PROGRESS, "Phase In Progress"),
        (PHASE_PENDING_TQA, "Phase Pending TQA"),
        (PHASE_PENDING_PQA, "Phase Pending PQA"),
        (PHASE_PENDING_DELIVERY, "Phase Pending Delivery"),
        (PHASE_COMPLETED, "Phase Completed"),
        (PHASE_POSTPONED, "Phase Postponed"),
        (PHASE_PRECHECKS_OVERDUE, "Phase Prechecks Overdue"),

        (LEAVE_SUBMITTED, "Leave Submitted"),
        (LEAVE_APPROVED, "Leave Approved"),
        (LEAVE_REJECTED, "Leave Rejected"),
        (LEAVE_CANCELLED, "Leave Cancelled"),

        (CLIENT_ONBOARDING_RENEWAL, "Onboarding Renewal Reminders"),
    )

    JOB_EVENTS = [
        JOB_CREATED,
        JOB_STATUS_CHANGE,
        JOB_PENDING_SCOPING,
        JOB_PENDING_SCOPE_SIGNOFF,
        JOB_SCOPING_COMPLETE,
        JOB_COMPLETE,
    ]

    PHASE_EVENTS = [
        PHASE_STATUS_CHANGE,
        PHASE_LATE_TO_TQA,
        PHASE_LATE_TO_PQA,
        PHASE_TQA_UPDATES,
        PHASE_PQA_UPDATES,
        PHASE_LATE_TO_DELIVERY,
        PHASE_NEW_NOTE,
        PHASE_FEEDBACK,
        PHASE_PENDING_SCHED,
        PHASE_SCHEDULED_CONFIRMED,
        PHASE_READY_PRECHECKS,
        PHASE_CLIENT_NOT_READY,
        PHASE_READY,
        PHASE_IN_PROGRESS,
        PHASE_PENDING_TQA,
        PHASE_PENDING_PQA,
        PHASE_PENDING_DELIVERY,
        PHASE_COMPLETED,
        PHASE_POSTPONED,
        PHASE_PRECHECKS_OVERDUE,

    ]

    LEAVE_EVENTS = [
        LEAVE_SUBMITTED,
        LEAVE_APPROVED,
        LEAVE_REJECTED,
        LEAVE_CANCELLED,
    ]
    
    CATEGORIES = {
        SYSTEM: "System",

        JOB_CREATED: "Job",
        JOB_STATUS_CHANGE: "Job",
        JOB_PENDING_SCOPING: "Job",
        JOB_PENDING_SCOPE_SIGNOFF: "Job",
        JOB_SCOPING_COMPLETE: "Job",
        JOB_COMPLETE: "Job",

        PHASE_STATUS_CHANGE: "Phase",
        PHASE_LATE_TO_TQA: "Phase",
        PHASE_LATE_TO_PQA: "Phase",
        PHASE_TQA_UPDATES: "Phase",
        PHASE_PQA_UPDATES: "Phase",
        PHASE_NEW_NOTE: "Phase",
        PHASE_FEEDBACK: "Phase",
        PHASE_LATE_TO_DELIVERY: "Phase",
        PHASE_PENDING_SCHED: "Phase",
        PHASE_SCHEDULED_CONFIRMED: "Phase",
        PHASE_READY_PRECHECKS: "Phase",
        PHASE_CLIENT_NOT_READY: "Phase",
        PHASE_READY: "Phase",
        PHASE_IN_PROGRESS: "Phase",
        PHASE_PENDING_TQA: "Phase",
        PHASE_PENDING_PQA: "Phase",
        PHASE_PENDING_DELIVERY: "Phase",
        PHASE_COMPLETED: "Phase",
        PHASE_POSTPONED: "Phase",
        PHASE_PRECHECKS_OVERDUE: "Phase",

        LEAVE_SUBMITTED: "Leave",
        LEAVE_APPROVED: "Leave",
        LEAVE_REJECTED: "Leave",
        LEAVE_CANCELLED: "Leave",

        CLIENT_ONBOARDING_RENEWAL: "Client",
    }