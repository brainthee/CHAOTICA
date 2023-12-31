from django.contrib.auth import login, authenticate
from django.shortcuts import render, redirect
from django.urls import reverse_lazy, reverse
from django.conf import settings as django_settings
from django.template import loader
from django.utils import timezone
from django.http import HttpResponseForbidden, JsonResponse, HttpResponse, HttpResponseRedirect, Http404, HttpResponseBadRequest
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
import json, os, random
from .forms import ChaoticaUserForm, LeaveRequestForm, ProfileBasicForm, CustomConfigForm, AssignRoleForm, InviteUserForm
from .enums import GlobalRoles, NotificationTypes
from .tasks import task_send_notifications
from .models import Notification, User, Language, Note, LeaveRequest, UserInvitation
from .utils import ext_reverse, AppNotification, is_valid_uuid
from django.db.models import Q
from django.db.models import Value as V
from django.db.models.functions import Concat
from dal import autocomplete
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.views import View
from guardian.shortcuts import get_objects_for_user
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.contrib import messages 
from django.shortcuts import get_object_or_404
from constance import config
from constance.forms import ConstanceForm
from constance.utils import get_values
from .tasks import task_update_holidays
from django.views.decorators.http import require_http_methods, require_safe, require_POST
    

def page_defaults(request):
    from jobtracker.models import Job, Phase
    context = {}
    context['notifications'] = Notification.objects.filter(user=request.user)
    context['config'] = config
    context['DJANGO_ENV'] = django_settings.DJANGO_ENV
    context['DJANGO_VERSION'] = django_settings.DJANGO_VERSION

    context['myJobs'] = Job.objects.jobs_for_user(request.user)
    context['myPhases'] = Phase.objects.phases_for_user(request.user)
    return context


def is_ajax(request):
    return request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'


@login_required
@require_safe
def update_holidays(request):
    task_update_holidays()
    return HttpResponse()
    task_update_holidays()
    return HttpResponseRedirect(reverse('home'))


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
    notice = AppNotification(
        NotificationTypes.SYSTEM,
        "Test Notification", "This is a test notification. At ease.",
        "emails/test_email.html"
    )
    task_send_notifications(notice, User.objects.filter(pk=request.user.pk))
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


@require_safe
def maintenance(request):
    if not django_settings.MAINTENANCE_MODE:
        return HttpResponseRedirect(reverse('home'))
    return render(request, 'maintenance.html')


@login_required
@require_safe
def view_own_leave(request):
    context = {}
    leave_list = LeaveRequest.objects.filter(user=request.user)
    context = {
        'leave_list': leave_list,
        }
    template = loader.get_template('view_own_leave.html')
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@login_required
@require_http_methods(["POST", "GET"])
def request_leave(request):
    if request.method == "POST":
        form = LeaveRequestForm(request.POST, request=request)
        if form.is_valid():
            leave = form.save(commit=False)
            leave.user = request.user
            leave.save()
            leave.send_request_notification()
            return HttpResponseRedirect(reverse('view_own_leave'))
    else:
        form = LeaveRequestForm(request=request)
    
    context = {'form': form}
    template = loader.get_template('forms/add_leave_form.html')
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@login_required
@require_safe
def manage_leave(request):
    context = {}
    from jobtracker.models.orgunit import OrganisationalUnit
    units_with_perm = get_objects_for_user(request.user, "can_view_all_leave_requests", OrganisationalUnit)
    leave_list = LeaveRequest.objects.filter(
        Q(user__unit_memberships__unit__in=units_with_perm) | # Show leave requests for users we have permission over
        Q(user__manager=request.user) | # where we're manager
        Q(user__acting_manager=request.user) | # where we're acting manager
        Q(user=request.user)) # and our own of course....
    context = {
        'leave_list': leave_list,
        }
    template = loader.get_template('manage_leave.html')
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
        if request.POST.get('user_action') == "approve_action":
            # Approve it!
            leave.authorise(request.user)
            data['form_is_valid'] = True

        elif request.POST.get('user_action') == "reject_action":
            # Decline!
            leave.decline(request.user)
            data['form_is_valid'] = True
        else:
            # invalid choice...
            return HttpResponseBadRequest()

    context = {'leave': leave,}
    data['html_form'] = loader.render_to_string("modals/leave_auth.html",
                                                context,
                                                request=request)
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
        if request.POST.get('user_action') == "approve_action":
            # Approve it!
            leave.cancel()
            data['form_is_valid'] = True
        else:
            # invalid choice...
            return HttpResponseBadRequest()

    context = {'leave': leave,}
    data['html_form'] = loader.render_to_string("modals/leave_cancel.html",
                                                context,
                                                request=request)
    return JsonResponse(data)

@login_required
@require_safe
def view_own_profile(request):
    from jobtracker.models import Skill, UserSkill
    context = {}
    skills = Skill.objects.all()
    languages = Language.objects.all()
    user_skills = UserSkill.objects.filter(user=request.user)
    profile_form = ProfileBasicForm(instance=request.user)
    context = {
        'skills': skills, 
        'userSkills': user_skills,
        'languages': languages,
        'profileForm': profile_form,
        'feed_url': ext_reverse(reverse('view_own_schedule_feed', kwargs={'cal_key':request.user.schedule_feed_id})),
        'feed_family_url': ext_reverse(reverse('view_own_schedule_feed_family', kwargs={'cal_key':request.user.schedule_feed_family_id})),
        }
    template = loader.get_template('profile.html')
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@login_required
@require_http_methods(["GET", "POST"])
def update_own_profile(request):
    data = {}
    data['form_is_valid'] = False
    if request.method == "POST":
        form = ProfileBasicForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            data['form_is_valid'] = True
            data['changed_data'] = form.changed_data
    else:
        form = ProfileBasicForm(instance=request.user)
    
    context = {'profileForm': form}
    data['html_form'] = loader.render_to_string("partials/profile/basic_profile_form.html",
                                                context,
                                                request=request)
    return JsonResponse(data)


@require_safe
def notifications_feed(request):
    if request.user.is_anonymous:
        return HttpResponseForbidden()
    data = {}
    data['notifications'] = []
    notifications = Notification.objects.filter(user=request.user)
    if is_ajax(request):
        for notice in notifications:
            data['notifications'].append({
                "title": notice.title,
                "msg": notice.message,
                "icon": notice.icon,
                "timestamp": notice.timestamp,
                "is_read": notice.is_read,
                "url": notice.link,
            }
        )    
        context = {'notifications': notifications,}
        data['html_form'] = loader.render_to_string("partials/notifications.html",
                                                    context,
                                                    request=request)
        return JsonResponse(data)
    else:
        return HttpResponseForbidden()


@login_required
@require_safe
def notifications_mark_read(request):
    notifications = Notification.objects.filter(user=request.user, is_read=False)
    for notice in notifications:
        notice.is_read = True
        notice.save()
    data = {
        'result': True
    }
    return JsonResponse(data, safe=False)


@login_required
@require_safe
def notification_mark_read(request, pk):
    notification = get_object_or_404(Notification, user=request.user, pk=pk, is_read=False)
    notification.is_read = True
    notification.save()
    data = {
        'result': True
    }
    return JsonResponse(data, safe=False)


@login_required
@require_safe
def update_own_theme(request):
    if 'mode' in request.GET:
        mode = request.GET.get('mode', 'light')
        valid_modes = ['dark', 'light']
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
                    user=request.user, skill=skill)
                if skill.rating != value:
                    skill.rating = value
                    skill.last_updated_on = timezone.now()
                    skill.save()
            except:
                # invalid skill!
                pass


        return HttpResponseRedirect(reverse('view_own_profile'))
    else:
        return HttpResponseRedirect(reverse('view_own_profile'))


@login_required
@require_http_methods(["GET", "POST"])
def update_own_certs(request):
    return HttpResponseBadRequest()


@staff_member_required
@require_http_methods(["GET", "POST"])
def app_settings(request):
    from pprint import pprint
    context = {}
    if request.method == "POST":
        form = ConstanceForm(request.POST.copy())
        if form.is_valid():
            form.save()
        else:
            pprint(form.errors)
            messages.error(request, "Form is invalid")
        return HttpResponseRedirect(reverse('app_settings'))
    else:
        # Send the modal
        form = ConstanceForm(initial=get_values())

    context = {'app_settings': form}
    template = loader.get_template('app_settings.html')
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@staff_member_required
@require_http_methods(["GET", "POST"])
def user_assign_global_role(request, email):
    user = get_object_or_404(User, email=email)
    data = dict()
    if request.method == 'POST':
        form = AssignRoleForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            data['form_is_valid'] = True         
        else:
            data['form_is_valid'] = False
    else:
        form = AssignRoleForm(instance=user)
    
    context = {'form': form,}
    data['html_form'] = loader.render_to_string("modals/assign_user_role.html",
                                                context,
                                                request=request)
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
    
    def get_context_data(self,*args, **kwargs):
        context = super(ChaoticaBaseView, self).get_context_data(*args,**kwargs)
        context = {**context, **page_defaults(self.request)}
        return context


class ChaoticaBaseGlobalRoleView(ChaoticaBaseView, UserPassesTestMixin):

    role_required = None

    def test_func(self):
        if self.role_required:
            return self.request.user.groups.filter(
                name=django_settings.GLOBAL_GROUP_PREFIX+GlobalRoles.CHOICES[self.role_required][1]).exists()
        else:
            return False


class ChaoticaBaseAdminView(ChaoticaBaseView, UserPassesTestMixin):

    def test_func(self):
        # Check if the user is in the global admin group
        return self.request.user.groups.filter(name=django_settings.GLOBAL_GROUP_PREFIX+GlobalRoles.CHOICES[GlobalRoles.ADMIN][1])


def log_system_activity(ref_obj, msg, author=None):
    new_note = Note(content=msg,
                 is_system_note=True,
                 author=author,
                 content_object=ref_obj)
    new_note.save()
    return new_note


@require_safe
def get_quote(request):
    lines = json.load(open(os.path.join(django_settings.BASE_DIR, 'chaotica_utils/templates/quotes.json')))
    random_index = random.randint(0, len(lines)-1)
    return JsonResponse(lines[random_index])


@login_required
@require_http_methods(["GET", "POST"])
def user_invite(request):
    data = {}
    data['form_is_valid'] = False
    if request.method == "POST":
        form = InviteUserForm(request.POST)
        if form.is_valid():
            invite = form.save(commit=False)
            invite.invited_by = request.user
            invite.save()
            invite.send_email()
            data['form_is_valid'] = True
    else:
        form = InviteUserForm()
    
    context = {'form': form}
    data['html_form'] = loader.render_to_string("modals/user_invite.html",
                                                context,
                                                request=request)
    return JsonResponse(data)


@require_http_methods(["POST", "GET"])
def signup(request, invite_id=None):
    invite = None
    if request.user.is_authenticated:
        return redirect('home')
    else:
        new_install = User.objects.all().count() <= 1
        # Check if we're invite only...
        if django_settings.USER_INVITE_ONLY and not new_install:
            if not invite_id or \
                not is_valid_uuid(invite_id) or \
                not UserInvitation.objects.filter(invite_id=invite_id).exists():
                context = {}
                template = loader.get_template('errors/invite_only.html')
                return HttpResponse(template.render(context, request))
            
            invite = get_object_or_404(UserInvitation, invite_id=invite_id)
            if invite.accepted:
                # Already accepted - rendor an error page
                context = {}
                template = loader.get_template('errors/invite_used.html')
                return HttpResponse(template.render(context, request))
            elif invite.is_expired():
                # Already accepted - rendor an error page
                context = {}
                template = loader.get_template('errors/invite_expired.html')
                return HttpResponse(template.render(context, request))
            else:
                if request.method == 'POST':
                    form = ChaoticaUserForm(request.POST, invite=invite)
                else:
                    form = ChaoticaUserForm(invite=invite)

        else:
            # Invitation isn't required - self sign up!
            if request.method == 'POST':
                form = ChaoticaUserForm(request.POST)
            else:
                form = ChaoticaUserForm()

        if request.method == 'POST' and form.is_valid():
            form.save()
            if invite:
                invite.accepted = True
                invite.save()
            email = form.cleaned_data.get('email')
            raw_password = form.cleaned_data.get('password1')
            user = authenticate(email=email, password=raw_password)
            login(request, user)
            return redirect('home')

        return render(request, 'signup.html', {'form': form})


class UserBaseView(ChaoticaBaseGlobalRoleView):
    model = User
    fields = '__all__'
    success_url = reverse_lazy('user_list')
    role_required = GlobalRoles.ADMIN

    def get_context_data(self, **kwargs):
        context = super(UserBaseView, self).get_context_data(**kwargs)
        return context

    def get_queryset(self) :
        queryset = User.objects.all().exclude(email="AnonymousUser")
        return queryset

class UserListView(UserBaseView, ListView):
    """View to list all jobs.
    Use the 'job_list' variable in the template
    to access all job objects"""

class UserDetailView(UserBaseView, DetailView):

    def get_object(self, queryset=None):
        if self.kwargs.get('email'):
            return get_object_or_404(User, email=self.kwargs.get('email'))
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


######################################
# Autocomplete fields
######################################

class UserAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        # Don't forget to filter out results depending on the visitor !
        if not self.request.user.is_authenticated:
            return User.objects.none()
        # TODO: Do permission checks...
        qs = User.objects.all().annotate(full_name=Concat('first_name', V(' '), 'last_name'))
        if self.q:
            qs = qs.filter(
                Q(email__icontains=self.q) |
                Q(full_name__icontains=self.q) |
                Q(first_name__icontains=self.q) |
                Q(last_name__icontains=self.q), is_active=True).order_by('email')
        return qs


@login_required
@require_POST
def site_search(request):
    data = {}
    context = {}
    q = request.POST.get('q', '').capitalize()
    results_count = 0
    from jobtracker.models import Job, Phase, Client, Service, Skill, BillingCode
    if is_ajax(request) and len(q) > 2:
        ## Jobs
        jobs_search = get_objects_for_user(request.user, 'jobtracker.view_job', Job.objects.all()).filter(
            Q(title__icontains=q) | Q(overview__icontains=q) | Q(slug__icontains=q)
                | Q(id__icontains=q))
        context['search_jobs'] = jobs_search
        results_count = results_count + jobs_search.count()

        ## Phases
        phases_search = Phase.objects.filter(
            Q(title__icontains=q) | Q(description__icontains=q) | Q(phase_id__icontains=q),
            job__in=jobs_search,)
        context['search_phases'] = phases_search
        results_count = results_count + phases_search.count()

        ## Clients
        cl_search = Client.objects.filter(
            Q(name__icontains=q))
        context['search_clients'] = cl_search
        results_count = results_count + cl_search.count()

        ## BillingCodes
        bc_search = BillingCode.objects.filter(
            Q(code__icontains=q))
        context['search_billingCodes'] = bc_search
        results_count = results_count + bc_search.count()

        ## Services
        sv_search = Service.objects.filter(
            Q(name__icontains=q))
        context['search_services'] = sv_search
        results_count = results_count + sv_search.count()

        ## Skills
        sk_search = Skill.objects.filter(
            Q(name__icontains=q))
        context['search_skills'] = sk_search
        results_count = results_count + sk_search.count()

        ## Users
        if request.user.is_superuser:
            us_search = User.objects.filter(
                Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
            )
            context['search_users'] = us_search
            results_count = results_count + us_search.count()
        
    context['results_count'] = results_count
    
    # Get research searches?
    context['recentSearches'] = None

    context['q'] = q
    data['html_form'] = loader.render_to_string("partials/search-results.html",
                                                context,
                                                request=request)

    return JsonResponse(data)