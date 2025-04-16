from chaotica_utils.models import User

_CRITERIA_REGISTRY = {}


def register_criteria(name):
    """Decorator to register a criteria function"""

    def decorator(func):
        _CRITERIA_REGISTRY[name] = func
        return func

    return decorator


def get_criteria_function(name):
    """Get a registered criteria function"""
    return _CRITERIA_REGISTRY.get(name)


@register_criteria("unit_members")
def unit_members(entity, params=None):
    """Return all members of the organizational unit"""

    unit = None
    if hasattr(entity, "unit"):
        unit = entity.unit
    elif hasattr(entity, "job") and hasattr(entity.job, "unit"):
        unit = entity.job.unit

    if unit:
        return User.objects.filter(unit_memberships__unit=unit, is_active=True)
    return User.objects.none()


@register_criteria("timeslot_assignees")
def timeslot_assignees(entity, params=None):
    """Return all users scheduled on the job or phase"""

    # Determine what type of entity we have
    if hasattr(entity, "timeslots"):
        # This is a phase
        return User.objects.filter(timeslots__phase=entity, is_active=True).distinct()
    elif hasattr(entity, "phases"):
        # This is a job
        return User.objects.filter(
            timeslots__phase__job=entity, is_active=True
        ).distinct()

    return User.objects.none()


@register_criteria("client_account_managers")
def client_account_managers(entity, params=None):
    """Return client account managers"""

    client = None
    if hasattr(entity, "client"):
        client = entity.client
    elif hasattr(entity, "job") and hasattr(entity.job, "client"):
        client = entity.job.client

    if client and hasattr(client, "account_managers"):
        return client.account_managers.filter(is_active=True)

    return User.objects.none()


@register_criteria("user_manager")
def user_manager(entity, params=None):
    """Return the user's manager and acting manager"""
    
    # Add the ability to specify the field to lookup the user
    user_field = "user"
    if params and "user_field" in params:
        user_field = params["user_field"]

    # For leave requests, the entity has a user field
    if hasattr(entity, user_field) and getattr(entity, user_field).manager:
        managers = [getattr(entity, user_field).manager]
        if getattr(entity, user_field).acting_manager:
            managers.append(getattr(entity, user_field).acting_manager)
        return User.objects.filter(pk__in=[m.pk for m in managers if m], is_active=True)

    return User.objects.none()


@register_criteria("user")
def user(entity, params=None):
    """Return the user"""

    # Add the ability to specify the field to lookup the user
    user_field = "user"
    if params and "user_field" in params:
        user_field = params["user_field"]

    # For leave requests, the entity has a user field
    if hasattr(entity, user_field):
        return User.objects.filter(pk=getattr(entity, user_field).pk, is_active=True)

    return User.objects.none()


@register_criteria("job_support_team")
def job_support_team(entity, params=None):
    """Return all members of a job's support team"""
    from jobtracker.models import Job

    job = None
    if isinstance(entity, Job):
        job = entity
    elif hasattr(entity, "job"):
        job = entity.job

    if job and hasattr(job, "job_support_roles"):
        support_team_users = [
            role.user for role in job.job_support_roles.all() if role.user
        ]
        return User.objects.filter(
            id__in=[user.id for user in support_team_users], is_active=True
        )

    return User.objects.none()


@register_criteria("team_members")
def team_members(entity, params=None):
    """Return all members of a team"""
    from jobtracker.models import Team

    team_id = None
    if params and "team_id" in params:
        team_id = params["team_id"]
    elif hasattr(entity, "team") and entity.team:
        team_id = entity.team.id

    if team_id:
        return User.objects.filter(
            teammember__team_id=team_id, is_active=True
        ).distinct()

    return User.objects.none()


@register_criteria("same_client_job_leads")
def same_client_job_leads(entity, params=None):
    """Return project leads for jobs from the same client"""
    from jobtracker.models import Job, Phase

    client = None
    if hasattr(entity, "client"):
        client = entity.client
    elif hasattr(entity, "job") and hasattr(entity.job, "client"):
        client = entity.job.client

    if not client:
        return User.objects.none()

    # Find all active jobs for this client
    active_jobs = Job.objects.filter(client=client).exclude(
        status__in=[4, 5]
    )  # Exclude deleted/archived

    # Collect all project leads from phases
    project_leads = []
    for job in active_jobs:
        for phase in job.phases.all():
            if phase.project_lead:
                project_leads.append(phase.project_lead.id)

    return User.objects.filter(id__in=project_leads, is_active=True).distinct()


@register_criteria("client_tech_account_managers")
def client_tech_account_managers(entity, params=None):
    """Return client technical account managers"""
    client = None
    if hasattr(entity, "client"):
        client = entity.client
    elif hasattr(entity, "job") and hasattr(entity.job, "client"):
        client = entity.job.client

    if client and hasattr(client, "tech_account_managers"):
        return client.tech_account_managers.filter(is_active=True)

    return User.objects.none()


@register_criteria("feedback_author")
def feedback_author(entity, params=None):
    """Return the author of feedback"""
    if hasattr(entity, "author") and entity.author:
        return User.objects.filter(id=entity.author.id, is_active=True)

    return User.objects.none()
