class NotificationTypes:
    JOB = 0
    PHASE = 1
    SCOPING = 2
    ORGUNIT = 3
    ADMIN = 4
    SYSTEM = 5


# Roles that apply across the whole site with no object specific permissions
class GlobalRoles:
    ANON = 0
    ADMIN = 1
    DELIVERY_MGR = 2
    SERVICE_DELIVERY = 3
    SALES_MGR = 4
    SALES_MEMBER = 5
    USER = 6

    DEFAULT_ROLE = USER
    CHOICES = (
        (ANON, "Anonymous"),
        (ADMIN, "Admin"),
        (DELIVERY_MGR, "Manager"),
        (SERVICE_DELIVERY, "Service Delivery"),
        (SALES_MGR, "Sales Manager"),
        (SALES_MEMBER, "Sales Member"),
        (USER, "User"),
    )
    BS_COLOURS = (
        (ANON, "light"),
        (ADMIN, "danger"),
        (DELIVERY_MGR, "warning"),
        (SERVICE_DELIVERY, "success"),
        (SALES_MGR, "info"),
        (SALES_MEMBER, "info"),
        (USER, "secondary"),
    )
    PERMISSIONS = (
        (ANON, []),
        (
            ADMIN,
            [
                # Client
                "jobtracker.view_client",
                "jobtracker.add_client",
                "jobtracker.change_client",
                "jobtracker.delete_client",
                "jobtracker.assign_account_managers_client",
                # Client Frameworks
                "jobtracker.view_frameworkagreement",
                "jobtracker.add_frameworkagreement",
                "jobtracker.change_frameworkagreement",
                "jobtracker.delete_frameworkagreement",
                # Client Contacts
                "jobtracker.view_contact",
                "jobtracker.add_contact",
                "jobtracker.change_contact",
                "jobtracker.delete_contact",
                # Service
                "jobtracker.view_service",
                "jobtracker.add_service",
                "jobtracker.change_service",
                "jobtracker.delete_service",
                # SkillCategory
                "jobtracker.view_skillcategory",
                "jobtracker.add_skillcategory",
                "jobtracker.change_skillcategory",
                "jobtracker.delete_skillcategory",
                # Skill
                "jobtracker.view_skill",
                "jobtracker.add_skill",
                "jobtracker.change_skill",
                "jobtracker.delete_skill",
                "jobtracker.view_users_skill",
                # OrganisationalUnit
                "jobtracker.view_organisationalunit",
                "jobtracker.add_organisationalunit",
                "jobtracker.change_organisationalunit",
                "jobtracker.delete_organisationalunit",
                "jobtracker.manage_members",
                "jobtracker.view_users_schedule",
                # qualification
                "jobtracker.view_qualification",
                "jobtracker.add_qualification",
                "jobtracker.change_qualification",
                "jobtracker.delete_qualification",
                "jobtracker.view_users_qualification",
                # Workflow tracking,
                "jobtracker.view_workflowtask",
                "jobtracker.add_workflowtask",
                "jobtracker.change_workflowtask",
                "jobtracker.delete_workflowtask",
                # Leave
                "chaotica_utils.manage_leave",
                # Billing Codes
                "jobtracker.view_billingcode",
                "jobtracker.add_billingcode",
                "jobtracker.change_billingcode",
                "jobtracker.delete_billingcode",
                # Users
                "chaotica_utils.manage_user",
                "chaotica_utils.impersonate_users",
                "chaotica_utils.manage_site_settings",
                "chaotica_utils.view_activity_logs",
            ],
        ),
        (
            DELIVERY_MGR,
            [
                # Client
                "jobtracker.view_client",
                # Client Frameworks
                "jobtracker.view_frameworkagreement",
                # Client Contacts
                "jobtracker.view_contact",
                # Service
                "jobtracker.view_service",
                "jobtracker.add_service",
                "jobtracker.change_service",
                "jobtracker.delete_service",
                # SkillCategory
                "jobtracker.view_skillcategory",
                "jobtracker.add_skillcategory",
                "jobtracker.change_skillcategory",
                "jobtracker.delete_skillcategory",
                # Skill
                "jobtracker.view_skill",
                "jobtracker.add_skill",
                "jobtracker.change_skill",
                "jobtracker.delete_skill",
                "jobtracker.view_users_skill",
                # OrganisationalUnit
                "jobtracker.view_organisationalunit",
                "jobtracker.view_users_schedule",
                # Workflow tracking,
                "jobtracker.view_workflowtask",
                # qualification
                "jobtracker.view_qualification",
                "jobtracker.add_qualification",
                "jobtracker.change_qualification",
                "jobtracker.delete_qualification",
                "jobtracker.view_users_qualification",
                # Users
                "jobtracker.manage_user",
                # Billing Codes
                "jobtracker.view_billingcode",
                "jobtracker.add_billingcode",
                "jobtracker.change_billingcode",
                "jobtracker.delete_billingcode",
                # Leave
                "chaotica_utils.manage_leave",
            ],
        ),
        (
            SERVICE_DELIVERY,
            [
                # Client
                "jobtracker.view_client",
                "jobtracker.add_client",
                "jobtracker.change_client",
                "jobtracker.delete_client",
                "jobtracker.assign_account_managers_client",
                # Client Frameworks
                "jobtracker.view_frameworkagreement",
                "jobtracker.add_frameworkagreement",
                "jobtracker.change_frameworkagreement",
                "jobtracker.delete_frameworkagreement",
                # Client Contacts
                "jobtracker.view_contact",
                # Service
                "jobtracker.view_service",
                # SkillCategory
                "jobtracker.view_skillcategory",
                # Skill
                "jobtracker.view_skill",
                "jobtracker.view_users_skill",
                # Workflow tracking,
                "jobtracker.view_workflowtask",
                # OrganisationalUnit
                "jobtracker.view_organisationalunit",
                "jobtracker.view_users_schedule",
                # qualification
                "jobtracker.view_qualification",
                "jobtracker.view_users_qualification",
                # Leave
                "chaotica_utils.manage_leave",
                # Billing Codes
                "jobtracker.view_billingcode",
                "jobtracker.add_billingcode",
            ],
        ),
        (
            SALES_MGR,
            [
                # Client
                "jobtracker.view_client",
                "jobtracker.add_client",
                "jobtracker.change_client",
                "jobtracker.delete_client",
                "jobtracker.assign_account_managers_client",
                # Client Frameworks
                "jobtracker.view_frameworkagreement",
                "jobtracker.add_frameworkagreement",
                "jobtracker.change_frameworkagreement",
                "jobtracker.delete_frameworkagreement",
                # Client Contacts
                "jobtracker.view_contact",
                "jobtracker.add_contact",
                "jobtracker.change_contact",
                "jobtracker.delete_contact",
                # Service
                "jobtracker.view_service",
                # SkillCategory
                "jobtracker.view_skillcategory",
                # Skill
                "jobtracker.view_skill",
                "jobtracker.view_users_skill",
                # OrganisationalUnit
                "jobtracker.view_organisationalunit",
                # qualification
                "jobtracker.view_qualification",
                "jobtracker.view_users_qualification",
                # Billing Codes
                "jobtracker.view_billingcode",
                "jobtracker.add_billingcode",
                "jobtracker.change_billingcode",
                "jobtracker.delete_billingcode",
            ],
        ),
        (
            SALES_MEMBER,
            [
                # Client
                "jobtracker.view_client",
                "jobtracker.add_client",
                # Client Frameworks
                "jobtracker.view_frameworkagreement",
                "jobtracker.add_frameworkagreement",
                # Client Contacts
                "jobtracker.view_contact",
                "jobtracker.add_contact",
                "jobtracker.change_contact",
                "jobtracker.delete_contact",
                # Service
                "jobtracker.view_service",
                # SkillCategory
                "jobtracker.view_skillcategory",
                # Skill
                "jobtracker.view_skill",
                "jobtracker.view_users_skill",
                # OrganisationalUnit
                "jobtracker.view_organisationalunit",
                # qualification
                "jobtracker.view_qualification",
                "jobtracker.view_users_qualification",
                # Billing Codes
                "jobtracker.view_billingcode",
                "jobtracker.add_billingcode",
            ],
        ),
        (
            USER,
            [
                # Client
                "jobtracker.view_client",
                # Client Frameworks
                "jobtracker.view_frameworkagreement",
                # Client Contacts
                "jobtracker.view_contact",
                # Service
                "jobtracker.view_service",
                # SkillCategory
                "jobtracker.view_skillcategory",
                # Skill
                "jobtracker.view_skill",
                "jobtracker.view_users_skill",
                # OrganisationalUnit
                "jobtracker.view_organisationalunit",
                # qualification
                "jobtracker.view_qualification",
                "jobtracker.view_users_qualification",
                # Billing Codes
                "jobtracker.view_billingcode",
            ],
        ),
    )


# These permissions are applied against specific units. Dependant jobs will use these permissions too
class UnitRoles:
    PENDING = 1
    CONSULTANT = 2
    SALES = 3
    SERVICE_DELIVERY = 4
    MANAGER = 5
    TQA = 6
    PQA = 7
    SCOPER = 8
    SUPERSCOPER = 9
    SCHEDULER = 10

    POOL_SCHEDULER = 11
    POOL_SCOPER = 12
    POOL_TQA = 13
    POOL_PQA = 14

    DEFAULTS = [
        {
            "pk": PENDING,
            "name": "Pending Approval",
            "bs_colour": "secondary",
            "default_role": False,
            "manage_role": False,
        },
        {
            "pk": CONSULTANT,
            "name": "Consultant",
            "bs_colour": "primary",
            "default_role": True,
            "manage_role": False,
        },
        {
            "pk": SALES,
            "name": "Sales",
            "bs_colour": "success",
            "default_role": False,
            "manage_role": False,
        },
        {
            "pk": SERVICE_DELIVERY,
            "name": "Service Delivery",
            "bs_colour": "info",
            "default_role": False,
            "manage_role": False,
        },
        {
            "pk": MANAGER,
            "name": "Manager",
            "bs_colour": "danger",
            "default_role": False,
            "manage_role": True,
        },
        {
            "pk": TQA,
            "name": "Tech QA'er",
            "bs_colour": "info",
            "default_role": False,
            "manage_role": False,
        },
        {
            "pk": PQA,
            "name": "Pres QA'er",
            "bs_colour": "info",
            "default_role": False,
            "manage_role": False,
        },
        {
            "pk": SCOPER,
            "name": "Scoper",
            "bs_colour": "info",
            "default_role": False,
            "manage_role": False,
        },
        {
            "pk": SUPERSCOPER,
            "name": "Super Scoper",
            "bs_colour": "info",
            "default_role": False,
            "manage_role": False,
        },
        {
            "pk": SCHEDULER,
            "name": "Scheduler",
            "bs_colour": "info",
            "default_role": False,
            "manage_role": False,
        },
        {
            "pk": POOL_SCHEDULER,
            "name": "Scheduling Pool",
            "bs_colour": "secondary",
            "default_role": False,
            "manage_role": False,
        },
        {
            "pk": POOL_SCOPER,
            "name": "Scoping Pool",
            "bs_colour": "secondary",
            "default_role": False,
            "manage_role": False,
        },
        {
            "pk": POOL_TQA,
            "name": "TQA Pool",
            "bs_colour": "secondary",
            "default_role": False,
            "manage_role": False,
        },
        {
            "pk": POOL_PQA,
            "name": "PQA Pool",
            "bs_colour": "secondary",
            "default_role": False,
            "manage_role": False,
        },
    ]

    @staticmethod
    def get_roles_with_permission(permission):
        allowed_add_roles = []
        for role in UnitRoles.PERMISSIONS:
            if permission in role[1]:
                allowed_add_roles.append(role[0])
        return allowed_add_roles

    PERMISSIONS = (
        (
            PENDING,
            [
                # None
            ],
        ),
        (
            CONSULTANT,
            [
                # Job
                "jobtracker.can_view_jobs",
                "jobtracker.view_job_schedule",
                "jobtracker.can_update_job",
                "jobtracker.can_add_note_job",
                "jobtracker.view_users_schedule",
                "jobtracker.view_organisationalunit",
            ],
        ),
        (
            SALES,
            [
                "jobtracker.view_organisationalunit",
                "jobtracker.can_view_jobs",
                "jobtracker.view_job_schedule",
                "jobtracker.can_update_job",
                "jobtracker.can_add_note_job",
                "jobtracker.view_users_schedule",
                "jobtracker.can_add_job",
                "jobtracker.can_assign_poc_job",
                # "jobtracker.can_manage_frameworkagreement_job",
            ],
        ),
        (
            SERVICE_DELIVERY,
            [
                "jobtracker.view_organisationalunit",
                "jobtracker.can_view_jobs",
                "jobtracker.view_job_schedule",
                "jobtracker.can_update_job",
                "jobtracker.can_add_note_job",
                "jobtracker.view_users_schedule",
                "jobtracker.can_refire_notifications_job",
                "jobtracker.can_schedule_job",
                "jobtracker.manage_members",
                # Leave
                "jobtracker.can_approve_leave_requests",
                "jobtracker.can_view_all_leave_requests",
            ],
        ),
        (
            MANAGER,
            [
                "jobtracker.can_view_jobs",
                "jobtracker.view_job_schedule",
                "jobtracker.can_update_job",
                "jobtracker.can_add_note_job",
                "jobtracker.can_refire_notifications_job",
                "jobtracker.view_users_schedule",
                # Org Unit
                "jobtracker.view_organisationalunit",
                "jobtracker.change_organisationalunit",
                "jobtracker.delete_organisationalunit",
                "jobtracker.manage_members",
                # Extras
                "jobtracker.can_scope_jobs",
                "jobtracker.can_assign_poc_job",
                # "jobtracker.can_manage_frameworkagreement_job",
                "jobtracker.can_signoff_scopes",
                "jobtracker.can_add_job",
                "jobtracker.can_delete_job",
                "jobtracker.can_add_phases",
                "jobtracker.can_delete_phases",
                "jobtracker.can_refire_notifications_job",
                # Leave
                "jobtracker.can_approve_leave_requests",
                "jobtracker.can_view_all_leave_requests",
                # Scope
                "jobtracker.can_signoff_own_scopes",
                # Scheduling
                "jobtracker.can_schedule_job",
            ],
        ),
        (
            TQA,
            [
                "jobtracker.can_tqa_jobs",
            ],
        ),
        (
            PQA,
            [
                "jobtracker.can_pqa_jobs",
            ],
        ),
        (
            SCOPER,
            [
                "jobtracker.can_scope_jobs",
                "jobtracker.can_signoff_scopes",
                "jobtracker.can_add_phases",
                "jobtracker.can_delete_phases",
            ],
        ),
        (
            SUPERSCOPER,
            [
                "jobtracker.can_scope_jobs",
                "jobtracker.can_signoff_scopes",
                "jobtracker.can_signoff_own_scopes",
            ],
        ),
        (
            SCHEDULER,
            [
                "jobtracker.can_schedule_job",
                "jobtracker.view_job_schedule",
                "jobtracker.view_users_schedule",
            ],
        ),
        (
            POOL_SCHEDULER,
            [
                "jobtracker.notification_pool_scheduling",
            ],
        ),
        (
            POOL_SCOPER,
            [
                "jobtracker.notification_pool_scoping",
            ],
        ),
        (
            POOL_TQA,
            [
                "jobtracker.notification_pool_tqa",
            ],
        ),
        (
            POOL_PQA,
            [
                "jobtracker.notification_pool_pqa",
            ],
        ),
    )


class LeaveRequestTypes:
    ANNUAL_LEAVE = 0
    TOIL = 1
    UNPAID_LEAVE = 2
    COMPASSIONATE_LEAVE = 3
    PATERNITY_MATERNITY = 4
    JURY_SERVICE = 5
    MILITARY_LEAVE = 6
    SICK = 7
    PUBLIC_HOLIDAY = 8
    NON_WORKING = 9
    EXCUSED = 10
    OTHER_APPROVED = 11
    OVERTIME_LEAVE = 12
    MEDICAL = 13
    SABBATICAL = 14

    CHOICES = (
        (ANNUAL_LEAVE, "Annual leave"),
        (TOIL, "Time Off in Lieu"),
        (UNPAID_LEAVE, "Unpaid leave"),
        (COMPASSIONATE_LEAVE, "Compassionate leave"),
        (PATERNITY_MATERNITY, "Paternity/Maternity"),
        (JURY_SERVICE, "Jury service"),
        (MILITARY_LEAVE, "Military leave"),
        (SICK, "Sick"),
        (PUBLIC_HOLIDAY, "Public Holiday"),
        (NON_WORKING, "Non-Working"),
        (EXCUSED, "Excused from Office"),
        (OTHER_APPROVED, "Other Approved"),
        (OVERTIME_LEAVE, "Overtime Leave"),
        (MEDICAL, "Medical Appointment"),
        (SABBATICAL, "Sabbatical Leave"),
    )

    # In time we'll refactor this to be better but for now...
    COUNT_TOWARDS_LEAVE = [
        ANNUAL_LEAVE,
    ]
