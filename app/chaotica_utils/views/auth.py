from django.contrib.auth import login, authenticate
from django.shortcuts import render, redirect
from django.template import loader
from django.http import (
    HttpResponseForbidden,
    JsonResponse,
    HttpResponse,
)
from ..forms.common import (
    ChaoticaUserForm,
    InviteUserForm,
)
from ..models import User, UserInvitation
from ..utils import is_valid_uuid
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from constance import config
from django.views.decorators.http import require_http_methods
from django.contrib.auth import views as auth_views
from django.urls import reverse


class LoginView(auth_views.LoginView):
    def get(self, request, *args, **kwargs):
        if config.ADFS_ENABLED and config.ADFS_AUTO_LOGIN:
            # Build ADFS URL with next parameter
            adfs_url = reverse('django_auth_adfs:login')
            try:
                # This method already validates the next parameter
                success_url = self.get_success_url()
            except:
                success_url = None
            
            if success_url:
                adfs_url += f"?next={success_url}"
            return redirect(adfs_url)
        
        return super().get(request, *args, **kwargs)


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
