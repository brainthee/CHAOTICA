from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponse,HttpResponseRedirect, HttpResponseBadRequest, JsonResponse, HttpResponseForbidden, HttpResponseNotFound
from django.template import loader, Template as tmpl, Context
from guardian.decorators import permission_required_or_403
from guardian.core import ObjectPermissionChecker
from guardian.mixins import PermissionListMixin, PermissionRequiredMixin
from django.views import View
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import log_system_activity, ChaoticaBaseView, pageDefaults
from chaotica_utils.utils import SendUserNotification
from ..models import *
from ..forms import *
from ..tasks import *
from .helpers import *
import logging
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages 
from django.apps import apps
import json


logger = logging.getLogger(__name__)


class OrganisationalUnitBaseView(ChaoticaBaseView):
    model = OrganisationalUnit
    fields = '__all__'

    def get_success_url(self):
        if 'slug' in self.kwargs:
            slug = self.kwargs['slug']
            return reverse_lazy('organisationalunit_detail', kwargs={'slug': slug})
        else:
            return reverse_lazy('organisationalunit_list')

class OrganisationalUnitListView(OrganisationalUnitBaseView, ListView):
    """View to list all jobs.
    Use the 'job_list' variable in the template
    to access all job objects"""

def OrganisationalUnit_join(request, slug):
    orgUnit = get_object_or_404(OrganisationalUnit, slug=slug)
    # Lets check they aren't already a member!
    if OrganisationalUnitMember.objects.filter(unit=orgUnit, member=request.user, left_date__isnull=True).exists():
        # Already a current member!
        return HttpResponseBadRequest()
    
    data = dict()
    if request.method == "POST":
        # Lets assume they want to if it's a POST!
        # Lets add the membership...
        membership = OrganisationalUnitMember.objects.create(unit=orgUnit, member=request.user)
        if membership:
            # Ok, lets see if we need to make it pending...
            if orgUnit.approval_required:
                membership.role = UnitRoles.PENDING
                messages.info(request, "Request to join unit "+orgUnit.name+" sent.")    
            else:
                # Add ourselves as inviter!
                membership.inviter = request.user     
                messages.info(request, "Joined Unit "+orgUnit.name)       
            membership.save()
            data['form_is_valid'] = True
        else:
            messages.error(request, "Error requesting membership. Please report this!")
            data['form_is_valid'] = False

    context = {'orgUnit': orgUnit}
    data['html_form'] = loader.render_to_string("jobtracker/modals/organisationalunit_join.html",
                                                context,
                                                request=request)
    return JsonResponse(data)


def OrganisationalUnit_review_join_request(request, slug, memberPK):
    orgUnit = get_object_or_404(OrganisationalUnit, slug=slug)
    
    # Only pass if the membership is pending...
    membership = get_object_or_404(OrganisationalUnitMember, unit=orgUnit, pk=memberPK, role=UnitRoles.PENDING)
    
    # Lets make sure our own membership is high enough level!
    ourMembership = get_object_or_404(OrganisationalUnitMember, member=request.user, unit=orgUnit, role=UnitRoles.MANAGER)

    # Okay, lets go!    
    data = dict()
    if request.method == "POST":
        # We need to check which button was pressed... accept or reject!
        if request.POST.get('user_action') == "approve_action":
            # Approve it!
            messages.info(request, "Accepted request from "+membership.member.get_full_name())
            membership.inviter = request.user
            membership.role = UnitRoles.CONSULTANT
            membership.save()
            # send a notification to the user
            SendUserNotification(membership.member, NotificationTypes.ORGUNIT, 
                                "Membership Accepted", "Your request to join "+orgUnit.name+" has been accepted", 
                                "emails/orgunit/accepted.html", orgUnit=orgUnit, membership=membership)
            data['form_is_valid'] = True

        elif request.POST.get('user_action') == "reject_action":
            # remove it!
            messages.warning(request, "Removed request from "+membership.member.get_full_name())
            membership.delete()
            # send a notification to the user
            SendUserNotification(membership.member, NotificationTypes.ORGUNIT, 
                                "Membership Rejected", "Your request to join "+orgUnit.name+" has been denied", 
                                "emails/orgunit/rejected.html", orgUnit=orgUnit, membership=membership)
            data['form_is_valid'] = True
        else:
            # invalid choice...
            return HttpResponseBadRequest()
            data['form_is_valid'] = False

    context = {'orgUnit': orgUnit, 'membership': membership}
    data['html_form'] = loader.render_to_string("jobtracker/modals/organisationalunit_review.html",
                                                context,
                                                request=request)
    return JsonResponse(data)

class OrganisationalUnitDetailView(OrganisationalUnitBaseView, DetailView):
    """View to list the details from one job.
    Use the 'job' variable in the template to access
    the specific job here and in the Views below"""

class OrganisationalUnitCreateView(OrganisationalUnitBaseView, CreateView):
    form_class = OrganisationalUnitForm
    fields = None

    def form_valid(self, form):
        # ensure the lead has manager access
        superResponse =  super(OrganisationalUnitCreateView, self).form_valid(form)
        orgUnit = form.save()
        membership, created = OrganisationalUnitMember.objects.get_or_create(
            unit=orgUnit, member=orgUnit.lead, role=UnitRoles.MANAGER)
        # Also add self in case we're not the lead
        if self.request.user is not orgUnit.lead:
            membership2, created2 = OrganisationalUnitMember.objects.get_or_create(
                unit=orgUnit, member=self.request.user, role=UnitRoles.MANAGER)
        return superResponse



class OrganisationalUnitUpdateView(OrganisationalUnitBaseView, UpdateView):
    form_class = OrganisationalUnitForm
    fields = None

class OrganisationalUnitDeleteView(OrganisationalUnitBaseView, DeleteView):
    """View to delete a job"""
    