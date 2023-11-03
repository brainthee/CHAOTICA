from django.shortcuts import get_object_or_404
from django.http import HttpResponseBadRequest, JsonResponse
from django.template import loader
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import ChaoticaBaseView
from chaotica_utils.utils import AppNotification, NotificationTypes
from chaotica_utils.tasks import task_send_notifications
from chaotica_utils.enums import UnitRoles
from chaotica_utils.models import User
from ..models import OrganisationalUnit, OrganisationalUnitMember
from ..forms import OrganisationalUnitForm, OrganisationalUnitMemberForm
import logging
from django.contrib import messages 


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

    
def organisationalunit_add(request, slug):
    org_unit = get_object_or_404(OrganisationalUnit, slug=slug)
    # Check we have permission to add...
    # TODO

    data = dict()
    if request.method == "POST":
        form = OrganisationalUnitMemberForm(request.POST, org_unit=org_unit)
        if form.is_valid():
            membership = form.save(commit=False)
            if membership:
                # Ok, lets see if we need to make it pending...
                if org_unit.approval_required:
                    membership.role = UnitRoles.PENDING
                    messages.info(request, "Request to join unit "+org_unit.name+" sent.")    
                else:
                    # Add ourselves as inviter!
                    membership.inviter = request.user     
                    messages.info(request, "Joined Unit "+org_unit.name)       
                membership.save()
                data['form_is_valid'] = True
        else:
            messages.error(request, "Error requesting membership. Please report this!")
            data['form_is_valid'] = False
    else:
        form = OrganisationalUnitMemberForm(org_unit=org_unit)


    context = {'orgUnit': org_unit, 'form': form}
    data['html_form'] = loader.render_to_string("jobtracker/modals/organisationalunit_add.html",
                                                context,
                                                request=request)
    return JsonResponse(data)

def organisationalunit_join(request, slug):
    org_unit = get_object_or_404(OrganisationalUnit, slug=slug)
    # Lets check they aren't already a member!
    if OrganisationalUnitMember.objects.filter(unit=org_unit, member=request.user, left_date__isnull=True).exists():
        # Already a current member!
        return HttpResponseBadRequest()
    
    data = dict()
    if request.method == "POST":
        # Lets assume they want to if it's a POST!
        # Lets add the membership...
        membership = OrganisationalUnitMember.objects.create(unit=org_unit, member=request.user)
        if membership:
            # Ok, lets see if we need to make it pending...
            if org_unit.approval_required:
                membership.role = UnitRoles.PENDING
                messages.info(request, "Request to join unit "+org_unit.name+" sent.")    
            else:
                # Add ourselves as inviter!
                membership.inviter = request.user     
                messages.info(request, "Joined Unit "+org_unit.name)       
            membership.save()
            data['form_is_valid'] = True
        else:
            messages.error(request, "Error requesting membership. Please report this!")
            data['form_is_valid'] = False

    context = {'orgUnit': org_unit}
    data['html_form'] = loader.render_to_string("jobtracker/modals/organisationalunit_join.html",
                                                context,
                                                request=request)
    return JsonResponse(data)


def organisationalunit_review_join_request(request, slug, member_pk):
    org_unit = get_object_or_404(OrganisationalUnit, slug=slug)
    
    # Only pass if the membership is pending...
    membership = get_object_or_404(OrganisationalUnitMember, unit=org_unit, pk=member_pk, role=UnitRoles.PENDING)
    
    # Lets make sure our own membership is high enough level!
    get_object_or_404(OrganisationalUnitMember, member=request.user, unit=org_unit, 
                                      role=UnitRoles.MANAGER)

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
            notice = AppNotification(NotificationTypes.ORGUNIT, 
                                "Membership Accepted", "Your request to join "+org_unit.name+" has been accepted", 
                                "emails/orgunit/accepted.html", orgUnit=org_unit, membership=membership)
            
            task_send_notifications(notice, User.objects.filter(pk=membership.member.pk))
            data['form_is_valid'] = True

        elif request.POST.get('user_action') == "reject_action":
            # remove it!
            messages.warning(request, "Removed request from "+membership.member.get_full_name())
            membership.delete()
            # send a notification to the user
            notice = AppNotification(NotificationTypes.ORGUNIT, 
                                "Membership Rejected", "Your request to join "+org_unit.name+" has been denied", 
                                "emails/orgunit/rejected.html", orgUnit=org_unit, membership=membership)
            
            task_send_notifications(notice, User.objects.filter(pk=membership.member.pk))
            data['form_is_valid'] = True
        else:
            # invalid choice...
            data['form_is_valid'] = False

    context = {'orgUnit': org_unit, 'membership': membership}
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
        super_response =  super(OrganisationalUnitCreateView, self).form_valid(form)
        org_unit = form.save()
        OrganisationalUnitMember.objects.get_or_create(
            unit=org_unit, member=org_unit.lead, role=UnitRoles.MANAGER)
        # Also add self in case we're not the lead
        if self.request.user is not org_unit.lead:
            OrganisationalUnitMember.objects.get_or_create(
                unit=org_unit, member=self.request.user, role=UnitRoles.MANAGER)
        return super_response



class OrganisationalUnitUpdateView(OrganisationalUnitBaseView, UpdateView):
    form_class = OrganisationalUnitForm
    fields = None

class OrganisationalUnitDeleteView(OrganisationalUnitBaseView, DeleteView):
    """View to delete a job"""
    