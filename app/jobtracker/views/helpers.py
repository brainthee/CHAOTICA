from django.http import HttpResponse,HttpResponseRedirect, HttpResponseBadRequest, JsonResponse, HttpResponseForbidden, HttpResponseNotFound
from django.template import loader, Template as tmpl, Context
from ..models import *
from ..forms import *
from ..tasks import *
import logging


logger = logging.getLogger(__name__)

def _process_assign_user(request, obj, prop, multiple=False, users=None):
    data = dict()
    if not request.user.has_perm('change_job', obj):
        return HttpResponseForbidden()
    if users is None:
        users = User.objects.filter(is_active=True)
    if request.method == 'POST':
        if multiple:
            form = AssignMultipleUser(request.POST, users=users)
        else:
            form = AssignUser(request.POST, users=users)

        if form.is_valid():
            if multiple:
                getattr(obj, prop).clear()
                for user in form.cleaned_data['users']:
                    getattr(obj, prop).add(user)
            else:
                setattr(obj, prop, form.cleaned_data['user'])
            
            obj.save()
            data['form_is_valid'] = True
        else:
            data['form_is_valid'] = False
    else:
        if multiple:
            form = AssignMultipleUser(users=users)
        else:
            form = AssignUser(users=users)
    
    context = {'form': form, 'obj': obj, 'field': obj._meta.get_field(prop).verbose_name.title(),}
    data['html_form'] = loader.render_to_string("modals/assign_user_modal.html",
                                                context,
                                                request=request)
    return JsonResponse(data)


def _process_assign_contact(request, obj, prop, multiple=False, contacts=None):
    data = dict()
    if contacts is None:
        contacts = Contact.objects.all()
    if request.method == 'POST':
        if multiple:
            form = AssignMultipleContacts(request.POST, contacts=contacts)
        else:
            form = AssignContact(request.POST, contacts=contacts)

        if form.is_valid():
            if multiple:
                getattr(obj, prop).clear()
                for user in form.cleaned_data['contacts']:
                    getattr(obj, prop).add(user)
            else:
                setattr(obj, prop, form.cleaned_data['contact'])
            
            obj.save()
            data['form_is_valid'] = True
        else:
            data['form_is_valid'] = False
    else:
        if multiple:
            form = AssignMultipleContacts(contacts=contacts)
        else:
            form = AssignContact(contacts=contacts)
    
    context = {'form': form, 'obj': obj, 'field': obj._meta.get_field(prop).verbose_name.title(),}
    data['html_form'] = loader.render_to_string("modals/assign_contact_modal.html",
                                                context,
                                                request=request)
    return JsonResponse(data)