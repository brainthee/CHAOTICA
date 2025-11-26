from django.urls import reverse_lazy, reverse
from django.conf import settings as django_settings
from django.template import loader
from django.utils import timezone
from django.http import (
    HttpResponseForbidden,
    JsonResponse,
    HttpResponse,
    HttpResponseRedirect,
)
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
import json, os, random, csv

from notifications.models.main import Notification
from ..forms.common import (
    ImportSiteDataForm,
    EditProfileForm,
    CustomConfigForm,
    DatabaseRestoreForm,
    MediaRestoreForm,
)
from ..mixins import PrefetchRelatedMixin
from ..enums import GlobalRoles
from ..models import User, Note, Quote
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.views import View
from guardian.decorators import permission_required_or_403
from django.views.generic.list import ListView
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from constance import config
from constance.utils import get_values
from django.views.decorators.http import (
    require_http_methods,
    require_safe,
)
from datetime import datetime, timedelta


def page_defaults(request):
    context = {}
    context["config"] = config
    
    context["DJANGO_ENV"] = django_settings.DJANGO_ENV
    context["DJANGO_VERSION"] = django_settings.DJANGO_VERSION

    if Quote.objects.filter(enabled=True).exists():
        context["quote"] = Quote.objects.filter(enabled=True).order_by('?')[0]

    context["DEMO_ENV"] = django_settings.DEMO_ENV
    context["DEMO_USER"] = django_settings.DEMO_USER
    context["DEMO_PASS"] = django_settings.DEMO_PASS
    # Calculate how long till reset
    now = timezone.now()
    
    reset_time = datetime.strptime(django_settings.DEMO_RESET_TIME, '%H:%M').time()

    # Create next reset datetime in the current timezone
    next_reset = timezone.datetime.combine(
        now.date(),
        reset_time,
        tzinfo=timezone.get_current_timezone()
    )

    # If we've already passed the reset time today, get tomorrow's
    if now.time() >= reset_time:
        next_reset += timedelta(days=1)

    # Calculate time remaining in seconds
    context["DEMO_TIME_REMAINING"] = next_reset

    # Figure out if it's our birthday!
    if (
        django_settings.CHAOTICA_BIRTHDAY.month == now.today().month
        and django_settings.CHAOTICA_BIRTHDAY.day == now.today().day
    ):
        context["IS_APP_BIRTHDAY"] = True
        context["CHAOTICA_BIRTHDAY_YEARS_OLD"] = (
            now.today().year - django_settings.CHAOTICA_BIRTHDAY.year
        )

    # Lets add prompts/messages if we need to...
    # Prompt for skills review...
    if request.user.is_authenticated and request.user.skills_last_updated():
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

    if request.user.is_authenticated and request.user.profile_last_updated:
        days_since_profile_updated = (
            timezone.now().date() - request.user.profile_last_updated
        ).days
        if days_since_profile_updated > config.PROFILE_REVIEW_DAYS:
            messages.info(
                request=request,
                message="It's time to review your profile! Please visit your Profile page",
            )
    return context


@require_safe
def maintenance(request):
    """
    Displays a maintenance page if we're in maintenance mode

    Args:
        request (Request): A request object

    Returns:
        HttpResponseRedirect, HttpResponse: Either the page or a redirect to home
    """
    if not config.MAINTENANCE_MODE:
        return HttpResponseRedirect(reverse("home"))
    template = loader.get_template("maintenance.html")
    context = {}
    return HttpResponse(template.render(context, request))


@staff_member_required
@require_http_methods(["POST", "GET"])
def map_view(request):
    context = {}
    active_users = User.objects.filter(is_active=True)
    context = {
        "active_users": active_users,
    }
    template = loader.get_template("map_view.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


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
        dbrestore_form = DatabaseRestoreForm()
        mediarestore_form = MediaRestoreForm()

    # Get or create API key for the user (if they have permissions)
    api_key = None
    api_key_last_used = None
    if request.user.is_superuser or request.user.is_staff:
        from ..models import HealthCheckAPIKey
        api_key_obj = HealthCheckAPIKey.get_or_create_for_user(request.user)
        api_key = str(api_key_obj.key)
        api_key_last_used = api_key_obj.last_used

    context = {
        "settings_form": settings_form,
        "import_form": import_form,
        "dbrestore_form": dbrestore_form,
        "mediarestore_form": mediarestore_form,
        "api_key": api_key,
        "api_key_last_used": api_key_last_used,
    }
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
                from ..impex.importers.smartsheets import SmartSheetCSVImporter

                importer = SmartSheetCSVImporter()
                job_output = importer.import_data(request, files)
            elif form.cleaned_data["importType"] == "ResourceManagerUserImporter":
                from ..impex.importers.resourcemanager_users import (
                    ResourceManagerUserImporter,
                )

                importer = ResourceManagerUserImporter()
                job_output = importer.import_data(request, files)
            elif form.cleaned_data["importType"] == "ResourceManagerProjectImporter":
                from ..impex.importers.resourcemanager_projects import (
                    ResourceManagerProjectImporter,
                )

                importer = ResourceManagerProjectImporter()
                job_output = importer.import_data(request, files)
            elif form.cleaned_data["importType"] == "CSVUserImporter":
                from ..impex.importers.csv_users import CSVUserImporter

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
        form = EditProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            obj = form.save()
            obj.profile_last_updated = timezone.now().today()
            obj.save()
            data["form_is_valid"] = True
            data["changed_data"] = form.changed_data
    else:
        form = EditProfileForm(instance=request.user)

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


class NoteListView(PrefetchRelatedMixin, NoteBaseView, ListView):
    prefetch_related = ["content_type"]

    def get_queryset(self):
        queryset = super(NoteListView, self).get_queryset()
        return queryset[:200]


@login_required
@require_http_methods(["POST"])
def regenerate_health_api_key(request):
    """Regenerate health check API key for the requesting user"""
    if not (request.user.is_superuser or request.user.is_staff):
        return JsonResponse({'error': 'Insufficient permissions'}, status=403)

    try:
        from ..models import HealthCheckAPIKey

        api_key = HealthCheckAPIKey.get_or_create_for_user(request.user)
        new_key = api_key.regenerate_key()

        return JsonResponse({
            'success': True,
            'new_key': str(new_key)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
