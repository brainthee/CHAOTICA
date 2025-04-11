class NotificationTypes:
    SYSTEM = 0
    JOB_STATUS_CHANGE = 1
    JOB_CREATED = 2
    PHASE_STATUS_CHANGE = 3
    PHASE_LATE_TO_TQA = 4
    PHASE_LATE_TO_PQA = 5
    PHASE_LATE_TO_DELIVERY = 6
    PHASE_NEW_NOTE = 12
    PHASE_TQA_UPDATES = 13
    PHASE_PQA_UPDATES = 14
    PHASE_FEEDBACK = 15

    # Leave notifications
    LEAVE_SUBMITTED = 7
    LEAVE_APPROVED = 8
    LEAVE_REJECTED = 9
    LEAVE_CANCELLED = 10
    
    CLIENT_ONBOARDING_RENEWAL = 11
    
    CHOICES = (
        (SYSTEM, "System Notification"),
        (JOB_STATUS_CHANGE, "Job Status Change"),
        (JOB_CREATED, "Job Created"),
        (PHASE_STATUS_CHANGE, "Phase Status Change"),
        (PHASE_LATE_TO_TQA, "Phase Late to TQA"),
        (PHASE_LATE_TO_PQA, "Phase Late to PQA"),
        (PHASE_TQA_UPDATES, "Phase TQA Updates"),
        (PHASE_PQA_UPDATES, "Phase PQA Updates"),
        (PHASE_LATE_TO_DELIVERY, "Phase Late to Delivery"),
        (PHASE_NEW_NOTE, "Phase Note Added"),
        (PHASE_FEEDBACK, "Phase Feedback"),
        (LEAVE_SUBMITTED, "Leave Submitted"),
        (LEAVE_APPROVED, "Leave Approved"),
        (LEAVE_REJECTED, "Leave Rejected"),
        (LEAVE_CANCELLED, "Leave Cancelled"),
        (CLIENT_ONBOARDING_RENEWAL, "Onboarding Renewal Reminders"),
    )
    
    CATEGORIES = {
        SYSTEM: "System",
        JOB_STATUS_CHANGE: "Job",
        JOB_CREATED: "Job",
        PHASE_STATUS_CHANGE: "Phase",
        PHASE_LATE_TO_TQA: "Phase",
        PHASE_LATE_TO_PQA: "Phase",
        PHASE_TQA_UPDATES: "Phase",
        PHASE_PQA_UPDATES: "Phase",
        PHASE_NEW_NOTE: "Phase",
        PHASE_FEEDBACK: "Phase",
        PHASE_LATE_TO_DELIVERY: "Phase",
        LEAVE_SUBMITTED: "Leave",
        LEAVE_APPROVED: "Leave",
        LEAVE_REJECTED: "Leave",
        LEAVE_CANCELLED: "Leave",
        CLIENT_ONBOARDING_RENEWAL: "Client",
    }