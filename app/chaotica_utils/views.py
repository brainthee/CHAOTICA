from django.contrib.auth import login, authenticate
from django.shortcuts import render, redirect
from django.urls import reverse_lazy, reverse
from django.conf import settings as django_settings
from django.template import loader
from django.utils import timezone
from django.db.models import TextField, Value
from django.db.models.functions import Concat
from django.http import (
    HttpResponseForbidden,
    JsonResponse,
    HttpResponse,
    HttpResponseRedirect,
    Http404,
    HttpResponseBadRequest,
)
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
import json, os, random, csv
from .forms import (
    ChaoticaUserForm,
    ImportSiteDataForm,
    LeaveRequestForm,
    ProfileBasicForm,
    ManageUserForm,
    CustomConfigForm,
    AssignRoleForm,
    InviteUserForm,
    MergeUserForm,
)
from .enums import GlobalRoles, NotificationTypes
from .tasks import (
    task_send_notifications,
    task_sync_global_permissions,
    task_sync_role_permissions,
    task_sync_role_permissions_to_default,
)
from dateutil.relativedelta import relativedelta
from .models import Notification, User, Language, Note, LeaveRequest, UserInvitation
from .utils import (
    ext_reverse,
    AppNotification,
    is_valid_uuid,
    clean_fullcalendar_datetime,
)
from django.db.models import Q
from django.db.models import Value as V
from django.db.models.functions import Concat
from dal import autocomplete
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.views import View
from guardian.shortcuts import get_objects_for_user
from guardian.decorators import permission_required_or_403
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.shortcuts import get_object_or_404
from constance import config
from constance.utils import get_values
import datetime
from .tasks import task_update_holidays
from django.views.decorators.http import (
    require_http_methods,
    require_safe,
    require_POST,
)


def page_defaults(request):
    from jobtracker.models import Job, Phase

    context = {}
    context["notifications"] = Notification.objects.filter(
        user=request.user, is_read=False
    ) | Notification.objects.filter(
        user=request.user, is_read=True
    )  # [10:]
    context["config"] = config
    if (
        django_settings.CHAOTICA_BIRTHDAY.month == datetime.date.today().month
        and django_settings.CHAOTICA_BIRTHDAY.day == datetime.date.today().day
    ):

        context["IS_APP_BIRTHDAY"] = True
        context["CHAOTICA_BIRTHDAY_YEARS_OLD"] = (
            datetime.date.today().year - django_settings.CHAOTICA_BIRTHDAY.year
        )

    context["DJANGO_ENV"] = django_settings.DJANGO_ENV
    context["DJANGO_VERSION"] = django_settings.DJANGO_VERSION

    context["myJobs"] = Job.objects.jobs_for_user(request.user)
    context["myPhases"] = Phase.objects.phases_for_user(request.user)

    # Lets add prompts/messages if we need to...
    # Prompt for skills review...
    if request.user.skills_last_updated():
        days_since_updated = (timezone.now() - request.user.skills_last_updated()).days
        if days_since_updated > config.SKILLS_REVIEW_DAYS:
            messages.info(
                request=request,
                message="It's time to review your skills! Please visit your Profile page",
            )
    else:
        messages.info(
            request=request,
            message="Make sure you remember to populate your skills! Please visit your Profile page",
        )

    if request.user.profile_last_updated:
        days_since_profile_updated = (
            timezone.now().date() - request.user.profile_last_updated
        ).days
        if days_since_profile_updated > config.PROFILE_REVIEW_DAYS:
            messages.info(
                request=request,
                message="It's time to review your profile! Please visit your Profile page",
            )
    return context


def is_ajax(request):
    return request.META.get("HTTP_X_REQUESTED_WITH") == "XMLHttpRequest"


@login_required
@staff_member_required
@require_safe
def update_holidays(request):
    task_update_holidays.do(request)
    return HttpResponse()
    return HttpResponseRedirect(reverse("home"))


@login_required
@staff_member_required
@require_safe
def sync_global_permissions(request):
    task_sync_global_permissions()
    return HttpResponse()
    return HttpResponseRedirect(reverse("home"))


@login_required
@staff_member_required
@require_safe
def sync_role_permissions_to_default(request):
    task_sync_role_permissions_to_default()
    return HttpResponse()
    return HttpResponseRedirect(reverse("home"))


@login_required
@staff_member_required
@require_safe
def sync_role_permissions(request):
    task_sync_role_permissions()
    return HttpResponse()
    return HttpResponseRedirect(reverse("home"))


@require_safe
def trigger_error(request):
    """
    Deliberately causes an error. Used to test error capturing

    Args:
        request (Request): A request object

    Returns:
        Exception: An error :)
    """
    division_by_zero = 1 / 0
    return division_by_zero


@require_safe
def test_notification(request):
    """
    Sends a test notification

    Args:
        request (Request): A request object

    Returns:
        HttpResponseRedirect: Redirect to the referer
    """
    notice = AppNotification(
        NotificationTypes.SYSTEM,
        "Test Notification",
        "This is a test notification. At ease.",
        "emails/test_email.html",
        None,
        reverse("home"),
    )
    task_send_notifications(notice, User.objects.filter(pk=request.user.pk))
    return HttpResponseRedirect(request.META.get("HTTP_REFERER"))


@require_safe
def maintenance(request):
    """
    Displays a maintenance page if we're in maintenance mode

    Args:
        request (Request): A request object

    Returns:
        HttpResponseRedirect, HttpResponse: Either the page or a redirect to home
    """
    if not django_settings.MAINTENANCE_MODE:
        return HttpResponseRedirect(reverse("home"))
    template = loader.get_template("maintenance.html")
    context = {}
    return HttpResponse(template.render(context, request))


@login_required
@require_http_methods(["POST", "GET"])
def view_own_leave(request):
    context = {}
    leave_list = LeaveRequest.objects.filter(user=request.user)
    context = {
        "leave_list": leave_list,
    }
    template = loader.get_template("view_own_leave.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@login_required
@require_http_methods(["POST", "GET"])
def request_own_leave(request):
    if request.method == "POST":
        form = LeaveRequestForm(request.POST, request=request)
        if form.is_valid():
            leave = form.save(commit=False)
            leave.user = request.user
            leave.save()
            leave.send_request_notification()
            return HttpResponseRedirect(reverse("view_own_leave"))
    else:
        form = LeaveRequestForm(request=request)

    context = {"form": form}
    template = loader.get_template("forms/add_leave_form.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@login_required
@require_safe
def manage_leave(request):
    context = {}
    from jobtracker.models.orgunit import OrganisationalUnit

    units_with_perm = get_objects_for_user(
        request.user, "can_view_all_leave_requests", OrganisationalUnit
    )

    leave_list = LeaveRequest.objects.filter(
        # Only show this last calendar's year...
        start_date__gte=timezone.now()
        - relativedelta(years=1),
    ).filter(
        Q(
            user__unit_memberships__unit__in=units_with_perm
        )  # Show leave requests for users we have permission over
        | Q(user__manager=request.user)  # where we're manager
        | Q(user__acting_manager=request.user)  # where we're acting manager
        | Q(user=request.user)  # and our own of course....
    )
    pending_leave = leave_list.filter(authorised=False, cancelled=False, declined=False).prefetch_related("user", "user__unit_memberships", "user__timeslots")
    leave_list = leave_list.exclude(authorised=False, cancelled=False, declined=False).prefetch_related("user", "user__unit_memberships", "user__timeslots")
    context = {
        "leave_list": leave_list,
        "pending_leave": pending_leave,
    }
    template = loader.get_template("manage_leave.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@login_required
def manage_leave_auth_request(request, pk):
    leave = get_object_or_404(LeaveRequest, pk=pk)
    # First, check we're allowed to process this...
    if not leave.can_user_auth(request.user):
        return HttpResponseForbidden()

    # Okay, lets go!
    data = dict()
    if request.method == "POST":
        # We need to check which button was pressed... accept or reject!
        if request.POST.get("user_action") == "approve_action":
            # Approve it!
            leave.authorise(request.user)
            data["form_is_valid"] = True

        elif request.POST.get("user_action") == "reject_action":
            # Decline!
            leave.decline(request.user)
            data["form_is_valid"] = True
        else:
            # invalid choice...
            return HttpResponseBadRequest()

    context = {
        "leave": leave,
    }
    data["html_form"] = loader.render_to_string(
        "modals/leave_auth.html", context, request=request
    )
    return JsonResponse(data)


@login_required
@require_http_methods(["GET", "POST"])
def cancel_own_leave(request, pk):
    leave = get_object_or_404(LeaveRequest, pk=pk, user=request.user)

    # Okay, lets go!
    data = dict()
    if request.method == "POST":
        # First, check we're allowed to process this...
        if not leave.can_cancel():
            return HttpResponseForbidden()

        # We need to check which button was pressed... accept or reject!
        if request.POST.get("user_action") == "approve_action":
            # Approve it!
            leave.cancel()
            data["form_is_valid"] = True
        else:
            # invalid choice...
            return HttpResponseBadRequest()

    context = {
        "leave": leave,
    }
    data["html_form"] = loader.render_to_string(
        "modals/leave_cancel.html", context, request=request
    )
    return JsonResponse(data)


@login_required
@require_safe
def view_own_profile(request):
    from jobtracker.models import Skill, UserSkill

    context = {}
    skills = Skill.objects.all().order_by("category", "name")
    languages = Language.objects.all()
    user_skills = UserSkill.objects.filter(user=request.user)
    profile_form = ProfileBasicForm(instance=request.user)
    context = {
        "skills": skills,
        "userSkills": user_skills,
        "languages": languages,
        "profileForm": profile_form,
        "feed_url": ext_reverse(
            reverse(
                "view_own_schedule_feed",
                kwargs={"cal_key": request.user.schedule_feed_id},
            )
        ),
        "feed_family_url": ext_reverse(
            reverse(
                "view_own_schedule_feed_family",
                kwargs={"cal_key": request.user.schedule_feed_family_id},
            )
        ),
    }
    template = loader.get_template("profile.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@login_required
@require_http_methods(["GET", "POST"])
def update_own_profile(request):
    data = {}
    data["form_is_valid"] = False
    if request.method == "POST":
        form = ProfileBasicForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            obj = form.save()
            obj.profile_last_updated = timezone.now().today()
            obj.save()
            data["form_is_valid"] = True
            data["changed_data"] = form.changed_data
    else:
        form = ProfileBasicForm(instance=request.user)

    context = {"profileForm": form}
    data["html_form"] = loader.render_to_string(
        "partials/profile/basic_profile_form.html", context, request=request
    )
    return JsonResponse(data)


@require_safe
def notifications_feed(request):
    data = {}
    data["notifications"] = []
    notifications = Notification.objects.none()

    if not request.user.is_authenticated:
        # Return an explicit 403 error to allow JS to redir
        return HttpResponseForbidden()

    if is_ajax(request):
        notifications = Notification.objects.filter(user=request.user)[:30]
        for notice in notifications:
            data["notifications"].append(
                {
                    "title": notice.title,
                    "msg": notice.message,
                    "icon": notice.icon,
                    "timestamp": notice.timestamp,
                    "is_read": notice.is_read,
                    "url": notice.link,
                }
            )

    context = {
        "notifications": notifications,
    }
    data["html_form"] = loader.render_to_string(
        "partials/notifications.html", context, request=request
    )
    return JsonResponse(data)


@login_required
@require_safe
def notifications_mark_read(request):
    notifications = Notification.objects.filter(user=request.user, is_read=False)
    for notice in notifications:
        notice.is_read = True
        notice.save()
    data = {"result": True}
    return JsonResponse(data, safe=False)


@login_required
@require_safe
def notification_mark_read(request, pk):
    notification = get_object_or_404(Notification, user=request.user, pk=pk)
    if not notification.is_read:
        notification.is_read = True
        notification.save()
    data = {"result": True}
    return JsonResponse(data, safe=False)


@login_required
@require_safe
def update_own_theme(request):
    if "mode" in request.GET:
        mode = request.GET.get("mode", "light")
        valid_modes = ["dark", "light", "auto"]
        if mode in valid_modes:
            request.user.site_theme = mode
            request.user.save()
            return HttpResponse("OK")
    return HttpResponseForbidden()


@login_required
@require_http_methods(["GET", "POST"])
def update_own_skills(request):
    from jobtracker.models import Skill, UserSkill

    if request.method == "POST":
        # Lets loop through the fields!
        for field in request.POST:
            # get skill..
            try:
                skill = Skill.objects.get(slug=field)
                value = int(request.POST.get(field))
                skill, _ = UserSkill.objects.get_or_create(
                    user=request.user, skill=skill
                )
                if skill.rating != value:
                    skill.rating = value
                    skill.last_updated_on = timezone.now()
                    skill.save()
            except:
                # invalid skill!
                pass

        return HttpResponseRedirect(reverse("view_own_profile"))
    else:
        return HttpResponseRedirect(reverse("view_own_profile"))


@login_required
@require_http_methods(["GET", "POST"])
def update_own_certs(request):
    return HttpResponseBadRequest()


@permission_required_or_403("chaotica_utils.manage_site_settings")
@require_http_methods(["GET", "POST"])
def app_settings(request):
    context = {}
    if request.method == "POST":
        settings_form = CustomConfigForm(initial=get_values())

        for key in settings_form.fields:
            value = request.POST.get(key)
            if key != "version" and key in settings_form.fields:
                field = settings_form.fields[key]
                clean_value = field.clean(field.to_python(value))
                setattr(config, key, clean_value)

        return HttpResponseRedirect(reverse("app_settings"))
    else:
        # Send the modal
        settings_form = CustomConfigForm(initial=get_values())
        import_form = ImportSiteDataForm()

    context = {"settings_form": settings_form, "import_form": import_form}
    template = loader.get_template("app_settings.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@login_required
@require_http_methods(["GET", "POST"])
def settings_import_data(request):
    data = {}
    data["form_is_valid"] = False
    job_output = ""

    if request.method == "POST":
        form = ImportSiteDataForm(request.POST, request.FILES)
        if form.is_valid():
            files = request.FILES.getlist("importFiles")
            if form.cleaned_data["importType"] == "SmartSheetCSVImporter":
                from .impex.importers.smartsheets import SmartSheetCSVImporter

                importer = SmartSheetCSVImporter()
                job_output = importer.import_data(request, files)
            elif form.cleaned_data["importType"] == "ResourceManagerUserImporter":
                from .impex.importers.resourcemanager_users import (
                    ResourceManagerUserImporter,
                )

                importer = ResourceManagerUserImporter()
                job_output = importer.import_data(request, files)
            elif form.cleaned_data["importType"] == "ResourceManagerProjectImporter":
                from .impex.importers.resourcemanager_projects import (
                    ResourceManagerProjectImporter,
                )

                importer = ResourceManagerProjectImporter()
                job_output = importer.import_data(request, files)
            elif form.cleaned_data["importType"] == "CSVUserImporter":
                from .impex.importers.csv_users import CSVUserImporter

                importer = CSVUserImporter()
                job_output = importer.import_data(request, files)

            data["form_is_valid"] = True
    else:
        form = ImportSiteDataForm()

    context = {
        "import_form": form,
        "job_output": job_output,
    }
    context = {**context, **page_defaults(request)}
    template = loader.get_template("forms/import_data_form.html")
    # data['html_form'] = loader.render_to_string("forms/import_data_form.html",
    #                                             context,
    #                                             request=request)
    # return JsonResponse(data)
    return HttpResponse(template.render(context, request))


@login_required
@require_http_methods(["GET", "POST"])
def settings_export_data(request):
    return HttpResponseForbidden()
    data = {}
    data["form_is_valid"] = False
    if request.method == "POST":
        form = ProfileBasicForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            obj = form.save()
            obj.profile_last_updated = timezone.now().today()
            obj.save()
            data["form_is_valid"] = True
            data["changed_data"] = form.changed_data
    else:
        form = ProfileBasicForm(instance=request.user)

    context = {"profileForm": form}
    data["html_form"] = loader.render_to_string(
        "partials/profile/basic_profile_form.html", context, request=request
    )
    return JsonResponse(data)


@permission_required_or_403("chaotica_utils.manage_user")
@require_http_methods(["GET"])
def csv_template_users(request):
    from impex.importers.csv_users import CSVUserImporter

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="chaotica_users.csv"'
    writer = csv.writer(response, delimiter=",")
    writer.writerow(CSVUserImporter.allowed_fields)
    return response


@permission_required_or_403("chaotica_utils.manage_user")
@require_http_methods(["GET", "POST"])
def user_merge(request, email):
    user = get_object_or_404(User, email=email)
    context = {}
    data = dict()
    if request.method == "POST":
        form = MergeUserForm(request.POST)
        if form.is_valid():
            # Lets merge!
            user_to_merge = form.cleaned_data["user_to_merge"]
            if user_to_merge == user:
                # Same user. GTFO
                data["form_is_valid"] = False
                form.add_error("user_to_merge", "You can't merge to the same user!")
            else:
                if user.merge(user_to_merge):
                    # Success
                    data["form_is_valid"] = True
                    messages.success(request, "User merged")
                else:
                    # Merge failed!
                    data["form_is_valid"] = False
                    form.add_error("", "Failed to merge!")
    else:
        # Send the modal
        form = MergeUserForm()

    context = {"form": form, "user": user}
    data["html_form"] = loader.render_to_string(
        "modals/user_merge.html", context, request=request
    )
    return JsonResponse(data)


@login_required
def user_schedule_timeslots(request, email):
    user = get_object_or_404(User, email=email)
    # Change FullCalendar format to DateTime
    start = clean_fullcalendar_datetime(request.GET.get("start", None))
    end = clean_fullcalendar_datetime(request.GET.get("end", None))
    data = user.get_timeslots(
        start=start,
        end=end,
    )
    return JsonResponse(data, safe=False)


@login_required
def user_schedule_holidays(request, email):
    user = get_object_or_404(User, email=email)
    # Change FullCalendar format to DateTime
    start = clean_fullcalendar_datetime(request.GET.get("start", None))
    end = clean_fullcalendar_datetime(request.GET.get("end", None))
    data = user.get_holidays(
        start=start,
        end=end,
    )
    return JsonResponse(data, safe=False)


@require_http_methods(["GET", "POST"])
# This is what we're doing in effect but we're doing it in the view
# @permission_required_or_403("chaotica_utils.manage_user")
def user_manage(request, email):
    user = get_object_or_404(User, email=email)
    context = {}
    # We want to either be their LM or have appropriate global perms...
    if (
        request.user == user.manager
        or request.user == user.acting_manager
        or request.user.has_perm("chaotica_utils.manage_user")
    ):
        if request.method == "POST":
            form = ManageUserForm(request.POST, instance=user)
            if form.is_valid():
                form.save()
        else:
            # Send the modal
            form = ManageUserForm(instance=user)

        context = {"form": form, "user": user}
        template = loader.get_template("chaotica_utils/user_detail_manage.html")
        context = {**context, **page_defaults(request)}
        return HttpResponse(template.render(context, request))
    else:
        # We don't have permission to manage this user...
        if request.user == user:
            # We can't manage ourselves! Redirect to our own profile
            return HttpResponseRedirect(reverse("view_own_profile"))
        else:
            return HttpResponseForbidden()


@permission_required_or_403("chaotica_utils.manage_user")
@require_http_methods(["GET", "POST"])
def user_manage_status(request, email, state):
    if state not in ["activate", "deactivate"]:
        return HttpResponseBadRequest()

    u = get_object_or_404(User, email=email)
    data = dict()
    if request.method == "POST":
        if u.is_active and state == "deactivate":
            u.is_active = False
            u.save()
            data["form_is_valid"] = True
        elif not u.is_active and state == "activate":
            u.is_active = True
            u.save()
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False

    context = {"u": u, "state": state}
    data["html_form"] = loader.render_to_string(
        "modals/user_manage_status.html", context, request=request
    )
    return JsonResponse(data)


@permission_required_or_403("chaotica_utils.manage_user")
@require_http_methods(["GET", "POST"])
def user_assign_global_role(request, email):
    user = get_object_or_404(User, email=email)
    data = dict()
    if request.method == "POST":
        form = AssignRoleForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
    else:
        form = AssignRoleForm(instance=user)

    context = {
        "form": form,
    }
    data["html_form"] = loader.render_to_string(
        "modals/assign_user_role.html", context, request=request
    )
    return JsonResponse(data)


class ChaoticaBaseView(LoginRequiredMixin, View):
    """Base view to enforce everything else"""

    def form_invalid(self, form):
        response = super().form_invalid(form)
        if self.request.accepts("text/html"):
            return response
        else:
            return JsonResponse(form.errors, status=400)

    def form_valid(self, form):
        # We make sure to call the parent's form_valid() method because
        # it might do some processing (in the case of CreateView, it will
        # call form.save() for example).
        response = super().form_valid(form)
        if self.request.accepts("text/html"):
            return response
        else:
            data = {
                "pk": self.object.pk,
            }
        return JsonResponse(data)

    def get_context_data(self, *args, **kwargs):
        context = super(ChaoticaBaseView, self).get_context_data(*args, **kwargs)
        context = {**context, **page_defaults(self.request)}
        return context


class ChaoticaBaseGlobalRoleView(ChaoticaBaseView, UserPassesTestMixin):

    role_required = None

    def test_func(self):
        if self.role_required:
            if self.role_required == "*":
                return self.request.user.groups.filter().exists()
            else:
                return self.request.user.groups.filter(
                    name=django_settings.GLOBAL_GROUP_PREFIX
                    + GlobalRoles.CHOICES[self.role_required][1]
                ).exists()
        else:
            return False


class ChaoticaBaseAdminView(ChaoticaBaseView, UserPassesTestMixin):

    def test_func(self):
        # Check if the user is in the global admin group
        return self.request.user.groups.filter(
            name=django_settings.GLOBAL_GROUP_PREFIX
            + GlobalRoles.CHOICES[GlobalRoles.ADMIN][1]
        )


def log_system_activity(ref_obj, msg, author=None):
    new_note = Note(
        content=msg, is_system_note=True, author=author, content_object=ref_obj
    )
    new_note.save()
    return new_note


@require_safe
def get_quote(request):
    lines = json.load(
        open(
            os.path.join(
                django_settings.BASE_DIR, "chaotica_utils/templates/quotes.json"
            )
        )
    )
    random_index = random.randint(0, len(lines) - 1)
    return JsonResponse(lines[random_index])


@login_required
@require_http_methods(["GET", "POST"])
def user_invite(request):
    if not config.INVITE_ENABLED:
        return HttpResponseForbidden()
    data = {}
    data["form_is_valid"] = False
    if request.method == "POST":
        form = InviteUserForm(request.POST)
        if form.is_valid():
            invite = form.save(commit=False)
            invite.invited_by = request.user
            invite.save()
            invite.send_email()
            data["form_is_valid"] = True
    else:
        form = InviteUserForm()

    context = {"form": form}
    data["html_form"] = loader.render_to_string(
        "modals/user_invite.html", context, request=request
    )
    return JsonResponse(data)


@require_http_methods(["POST", "GET"])
def signup(request, invite_id=None):
    invite = None
    if request.user.is_authenticated:
        return redirect("home")
    else:
        new_install = User.objects.all().count() <= 1
        # Ok, despite everything, if it's a new install... lets go!
        if new_install:
            if request.method == "POST":
                form = ChaoticaUserForm(request.POST)
            else:
                form = ChaoticaUserForm()
        else:
            if (
                invite_id
                and is_valid_uuid(invite_id)
                and UserInvitation.objects.filter(invite_id=invite_id).exists()
            ):
                # Valid invite
                invite = get_object_or_404(UserInvitation, invite_id=invite_id)
                if invite.accepted:
                    # Already accepted - rendor an error page
                    context = {}
                    template = loader.get_template("errors/invite_used.html")
                    return HttpResponse(template.render(context, request))
                elif invite.is_expired():
                    # Already accepted - rendor an error page
                    context = {}
                    template = loader.get_template("errors/invite_expired.html")
                    return HttpResponse(template.render(context, request))
                else:
                    if request.method == "POST":
                        form = ChaoticaUserForm(request.POST, invite=invite)
                    else:
                        form = ChaoticaUserForm(invite=invite)
            else:
                # Invalid invite (non existant or invalid - doesn't matter for our purpose)
                if config.REGISTRATION_ENABLED:
                    if request.method == "POST":
                        form = ChaoticaUserForm(request.POST)
                    else:
                        form = ChaoticaUserForm()
                else:
                    # Return registration disabled error
                    context = {}
                    template = loader.get_template("errors/registration_disabled.html")
                    return HttpResponse(template.render(context, request))

        if request.method == "POST" and form.is_valid():
            form.save()
            if invite:
                invite.accepted = True
                invite.save()
            email = form.cleaned_data.get("email")
            raw_password = form.cleaned_data.get("password1")
            user = authenticate(email=email, password=raw_password)
            login(request, user)
            return redirect("home")

        return render(request, "signup.html", {"form": form})


class UserBaseView(ChaoticaBaseGlobalRoleView):
    model = User
    fields = "__all__"
    success_url = reverse_lazy("user_list")
    role_required = GlobalRoles.ADMIN

    def get_context_data(self, **kwargs):
        context = super(UserBaseView, self).get_context_data(**kwargs)
        return context

    def get_queryset(self):
        queryset = User.objects.all().exclude(email="AnonymousUser")
        return queryset


class UserListView(UserBaseView, ListView):
    """View to list all jobs.
    Use the 'job_list' variable in the template
    to access all job objects"""

    def get_context_data(self, **kwargs):
        context = super(UserBaseView, self).get_context_data(**kwargs)
        invite_list = UserInvitation.objects.filter(accepted=False)
        context["invite_list"] = invite_list
        return context


class UserDetailView(UserBaseView, DetailView):
    role_required = "*"  # Allow all users with a role to view "public profiles"

    def get_object(self, queryset=None):
        if self.kwargs.get("email"):
            return get_object_or_404(User, email=self.kwargs.get("email"))
        else:
            raise Http404()


class UserCreateView(UserBaseView, CreateView):
    form_class = ChaoticaUserForm
    fields = None

    def form_valid(self, form):
        return super(UserCreateView, self).form_valid(form)


class UserUpdateView(UserBaseView, UpdateView):
    form_class = ChaoticaUserForm
    fields = None


class UserDeleteView(UserBaseView, DeleteView):
    """View to delete a job"""


class NoteBaseView(ChaoticaBaseGlobalRoleView):
    model = Note
    fields = "__all__"
    success_url = reverse_lazy("view_activity")
    role_required = GlobalRoles.ADMIN

    def get_context_data(self, **kwargs):
        context = super(NoteBaseView, self).get_context_data(**kwargs)
        return context

    def get_queryset(self):
        queryset = Note.objects.all()
        return queryset


class NoteListView(NoteBaseView, ListView):
    """View to list all Notes.
    Use the 'job_list' variable in the template
    to access all job objects"""


######################################
# Autocomplete fields
######################################


class UserAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        # Don't forget to filter out results depending on the visitor !
        if not self.request.user.is_authenticated:
            return User.objects.none()
        # TODO: Do permission checks...
        qs = User.objects.all().annotate(
            full_name=Concat("first_name", V(" "), "last_name")
        )
        if self.q:
            qs = qs.filter(
                Q(email__icontains=self.q)
                | Q(full_name__icontains=self.q)
                | Q(first_name__icontains=self.q)
                | Q(last_name__icontains=self.q),
                is_active=True,
            )
        return qs


@login_required
@require_POST
def site_search(request):
    data = {}
    context = {}
    q = request.POST.get("q", "")
    results_count = 0
    from jobtracker.models import (
        Job,
        Phase,
        Client,
        Service,
        Skill,
        BillingCode,
        Qualification,
        Accreditation,
        Project,
        OrganisationalUnit,
    )

    if is_ajax(request) and len(q) > 2:
        ## Jobs
        units_with_job_perms = get_objects_for_user(
            request.user, "jobtracker.can_view_jobs", OrganisationalUnit
        )

        jobs_search = Job.objects.filter(
            Q(title__icontains=q)
            | Q(overview__icontains=q)
            | Q(slug__icontains=q)
            | Q(id__icontains=q),
            unit__in=units_with_job_perms,
        )  # [:50]
        context["search_jobs"] = jobs_search
        results_count = results_count + jobs_search.count()

        ## Phases
        phases_search = Phase.objects.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(phase_id__icontains=q),
            job__unit__in=units_with_job_perms,
        )  # [:50]
        context["search_phases"] = phases_search
        results_count = results_count + phases_search.count()

        ## Clients
        cl_search = get_objects_for_user(
            request.user, "jobtracker.view_client", Client
        ).filter(
            Q(name__icontains=q)
        )  # [:50]
        context["search_clients"] = cl_search
        results_count = results_count + cl_search.count()

        ## BillingCodes
        bc_search = get_objects_for_user(
            request.user, "jobtracker.view_billingcode", BillingCode
        ).filter(
            Q(code__icontains=q)
        )  # [:50]
        context["search_billingCodes"] = bc_search
        results_count = results_count + bc_search.count()

        ## Services
        sv_search = get_objects_for_user(
            request.user, "jobtracker.view_service", Service
        ).filter(
            Q(name__icontains=q)
        )  # [:50]
        context["search_services"] = sv_search
        results_count = results_count + sv_search.count()

        ## Skills
        sk_search = get_objects_for_user(
            request.user, "jobtracker.view_skill", Skill
        ).filter(
            Q(name__icontains=q)
        )  # [:50]
        context["search_skills"] = sk_search
        results_count = results_count + sk_search.count()

        ## Qualifications
        qual_search = get_objects_for_user(
            request.user, "jobtracker.view_qualification", Qualification
        ).filter(
            Q(name__icontains=q)
        )  # [:50]
        context["search_quals"] = qual_search
        results_count = results_count + qual_search.count()

        ## Accreditation
        accred_search = get_objects_for_user(
            request.user, "jobtracker.view_accreditation", Accreditation
        ).filter(
            Q(name__icontains=q)
        )  # [:50]
        context["search_accred"] = accred_search
        results_count = results_count + accred_search.count()

        ## Projects
        project_search = get_objects_for_user(request.user, "*", Project).filter(
            Q(title__icontains=q)
        )  # [:50]
        context["search_project"] = project_search
        results_count = results_count + project_search.count()

        ## Users
        us_search = User.objects.annotate(
            full_name=Concat(
                "first_name", Value(" "), "last_name", output_field=TextField()
            )
        ).filter(
            Q(full_name__icontains=q) | Q(email__icontains=q)
        )  # [:50]

        context["search_users"] = us_search
        results_count = results_count + us_search.count()

    context["results_count"] = results_count

    context["q"] = q
    data["html_form"] = loader.render_to_string(
        "partials/search-results.html", context, request=request
    )

    return JsonResponse(data)
