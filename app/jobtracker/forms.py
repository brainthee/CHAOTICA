from django import forms
from django.urls import reverse
from .models import Contact, Job, Feedback, TimeSlot, TimeSlotType, Client, Phase, OrganisationalUnit, OrganisationalUnitMember, Skill, Service, WorkflowTask, SkillCategory
from chaotica_utils.models import Note, User
from .enums import DefaultTimeSlotTypes
from crispy_forms.helper import FormHelper
from crispy_forms.bootstrap import StrictButton, Accordion, AccordionGroup
from crispy_forms.layout import Layout, Row, Column, Field, Div, HTML, Submit, Reset
from crispy_bootstrap5.bootstrap5 import FloatingField
from dal import autocomplete
from chaotica_utils.enums import UnitRoles
from bootstrap_datepicker_plus.widgets import TimePickerInput, DatePickerInput, DateTimePickerInput



class SchedulerFilter(forms.Form):
    skills_specialist = forms.ModelMultipleChoiceField(required=False, label="Specialist",
                                    queryset=Skill.objects.all(),
                                    widget=autocomplete.ModelSelect2Multiple(),)
    skills_can_do_alone = forms.ModelMultipleChoiceField(required=False, label="Can Do Alone",
                                    queryset=Skill.objects.all(),
                                    widget=autocomplete.ModelSelect2Multiple(),)
    skills_can_do_support = forms.ModelMultipleChoiceField(required=False, label="Can Do With Support",
                                    queryset=Skill.objects.all(),
                                    widget=autocomplete.ModelSelect2Multiple(),)
    services = forms.ModelMultipleChoiceField(required=False,
                                    queryset=Service.objects.all(),
                                    widget=autocomplete.ModelSelect2Multiple(),)
    
    services = forms.ModelMultipleChoiceField(required=False,
                                    queryset=Service.objects.all(),
                                    widget=autocomplete.ModelSelect2Multiple(),)
    from_date = forms.DateField(required=False,
                            widget=DatePickerInput(),)
    to_date = forms.DateField(required=False,
                            widget=DatePickerInput(),)

    users = forms.ModelMultipleChoiceField(required=False,
        queryset=User.objects.filter(is_active=True),
        widget=autocomplete.ModelSelect2Multiple(url='user-autocomplete',
                                         attrs={
                                            'data-minimum-input-length': 3,
                                         },),)
    
    def __init__(self, *args, **kwargs):
        super(SchedulerFilter, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_method = 'get'
        self.helper.form_class = 'form-inline'
        self.helper.layout = Layout(
            Row(
                Column(
                    # Reset("reset-button", "Reset",  css_class="btn-phoenix-secondary"),
                    css_class="col"),
                Column(
                    Submit("apply", 'Apply', css_class="btn-phoenix-success"),
                    css_class="col-md-auto"),
            ),
            Accordion(
                # AccordionGroup('Date Filter',
                #     'from_date',
                #     'to_date',
                # ),
                AccordionGroup('Users Filter',
                    Field('users', css_class="extra", style="width: 100%;"),
                ),
                AccordionGroup('Skills Filter',
                    Field('skills_specialist', css_class="extra", style="width: 100%;"),
                    Field('skills_can_do_alone', css_class="extra", style="width: 100%;"),
                    Field('skills_can_do_support', css_class="extra", style="width: 100%;"),
                ),
                AccordionGroup('Service Filter',
                    Field('services', css_class="extra", style="width: 100%;"),
                ),
            ),
        )

    class Meta:
        fields = ('skills_specialist', 'skills_can_do_alone', 'skills_can_do_support', 
                  'users', 'services',
                  'from_date', 'to_date',)
        


class AssignContact(forms.Form):
    contact = forms.ModelChoiceField(required=False,
                                     queryset=Contact.objects.all(),)
    def __init__(self, *args, **kwargs):
        if 'contacts' in kwargs:
            contacts = kwargs.pop('contacts')
        super(AssignContact, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        if contacts:
            self.fields['contact'].queryset = contacts
        self.helper.layout = Layout(
            Div(
                Row(
                    Div(Field('contact'),
                        css_class="input-group input-group-dynamic")
                ),
                css_class='modal-body pt-3'),

            Div(
                Div(StrictButton("Save", type="submit", 
                    css_class="btn btn-outline-phoenix-success ms-auto mb-0"),
                css_class="button-row d-flex mt-4"),
            css_class="modal-footer"),
        )

class AssignMultipleContacts(forms.Form):
    contacts = forms.ModelMultipleChoiceField(required=False,
                                     queryset=Contact.objects.all(),)
    def __init__(self, *args, **kwargs):
        if 'contacts' in kwargs:
            contacts = kwargs.pop('contacts')
        super(AssignMultipleContacts, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        if contacts:
            self.fields['contacts'].queryset = contacts
        self.helper.layout = Layout(
            Div(
                Row(
                    Div(Field('contacts'),
                        css_class="input-group input-group-dynamic")
                ),
                css_class='modal-body pt-3'),

            Div(
                Div(StrictButton("Save", type="submit", 
                    css_class="btn btn-outline-phoenix-success ms-auto mb-0"),
                css_class="button-row d-flex mt-4"),
            css_class="modal-footer"),
        )


class AssignUserField(forms.Form):
    user = forms.ModelChoiceField(required=False,
        queryset=User.objects.filter(is_active=True),
        widget=autocomplete.ModelSelect2(url='user-autocomplete',
                                         attrs={
                                            'data-minimum-input-length': 3,
                                         },),)
    def __init__(self, *args, **kwargs):
        super(AssignUserField, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields['user'].help_text = None
        self.fields['user'].label = False
        self.helper.layout = Layout(
                Field('user', style="width: 100%;"),
                StrictButton('Add', id="addUserToResource",
                css_class="btn btn-outline-phoenix-success"),
        )

class AssignUser(forms.Form):
    user = forms.ModelChoiceField(required=False,
        queryset=User.objects.filter(is_active=True),
        widget=autocomplete.ModelSelect2(url='user-autocomplete',
                                         attrs={
                                             'data-minimum-input-length': 3,
                                         },),)
    def __init__(self, *args, **kwargs):
        if 'users' in kwargs:
            users = kwargs.pop('users')
        super(AssignUser, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        if users:
            self.fields['user'].queryset = users
        self.fields['user'].help_text = None
        self.fields['user'].label = None
        self.helper.form_show_labels = False
        self.helper.layout = Layout(
            Div(
                Row(
                    Field('user', style="width: 100%;"),
                ),
                css_class='modal-body p-3'),

            Div(
                Div(StrictButton("Save", type="submit", 
                    css_class="btn btn-outline-phoenix-success ms-auto mb-0"),
                css_class="button-row d-flex mt-4"),
            css_class="modal-footer"),
        )

class AssignMultipleUser(forms.Form):
    users = forms.ModelMultipleChoiceField(
        required=False,
        queryset=User.objects.filter(is_active=True),
        widget=autocomplete.ModelSelect2Multiple(url='user-autocomplete',
                                         attrs={
                                             'data-minimum-input-length': 3,
                                         },),)
    def __init__(self, *args, **kwargs):
        if 'users' in kwargs:
            users = kwargs.pop('users')
        super(AssignMultipleUser, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        if users:
            self.fields['users'].queryset = users
        self.helper.layout = Layout(
            Div(
                Row(
                    Field('users', style="width: 100%;"),
                ),
                css_class='modal-body pt-3'),

            Div(
                Div(StrictButton("Save", type="submit", 
                    css_class="btn btn-outline-phoenix-success ms-auto mb-0"),
                css_class="button-row d-flex mt-4"),
            css_class="modal-footer"),
        )


##########################
# Add Note form
##########################
class AddNote(forms.ModelForm):
    content = forms.CharField()

    def __init__(self, *args, **kwargs):
        super(AddNote, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields['content'].help_text = None
        self.fields['content'].label = None
        self.helper.form_show_labels = False

    class Meta:
        model = Note
        fields = ('content',)


##########################
# Add Feedback form
##########################
class FeedbackForm(forms.ModelForm):
    body = forms.CharField()

    def __init__(self, *args, **kwargs):
        super(FeedbackForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields['body'].help_text = None
        self.fields['body'].label = None
        self.helper.form_tag = False
        self.helper.form_show_labels = False

    class Meta:
        model = Feedback
        fields = ('body',)


class NonDeliveryTimeSlotModalForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        start=None
        if 'start' in kwargs:
            start = kwargs.pop('start')
        end=None
        if 'end' in kwargs:
            end = kwargs.pop('end')
        resource_id=None
        if 'resource_id' in kwargs:
            resource_id = kwargs.pop('resource_id')
        
        super(NonDeliveryTimeSlotModalForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        for fieldname in self.fields:
            self.fields[fieldname].help_text = None
        if self.instance.pk:
            delete_button = StrictButton("Delete", type="button", 
                data_url=reverse('delete_scheduler_slot', kwargs={"pk":self.instance.pk}),
                css_class="btn js-load-modal-form btn-outline-phoenix-danger me-auto mb-0")
        else:
            delete_button = None
        self.fields['user'].widget = forms.HiddenInput()
        self.fields['user'].disabled = True
        self.fields['phase'].disabled = True
        self.fields['start'].widget = DateTimePickerInput()
        self.fields['end'].widget = DateTimePickerInput()
        if not self.instance.pk:
            self.fields['start'].initial = start
            self.fields['end'].initial = end
            self.fields['user'].initial = User.objects.get(pk=resource_id)
        self.fields['slot_type'].queryset = TimeSlotType.objects.filter(is_assignable=True)
        self.helper.layout = Layout(
            Field('user', style="width: 100%;"),
            Field('phase', type="hidden"),
            Div(
                Row(
                    Column(Div(FloatingField('slot_type'),
                            css_class="input-group input-group-dynamic")),
                ),
                Row(
                    Column(Div(Field('start'),
                            css_class="input-group input-group-dynamic")),
                    Column(Div(Field('end'),
                            css_class="input-group input-group-dynamic")),
                ),
                css_class='card-body p-3'),
            Div(
                Div(
                    delete_button,
                    StrictButton("Save", type="submit", 
                        css_class="btn btn-outline-phoenix-success ms-auto mb-0"),
                    css_class="button-row d-flex"),
                css_class="card-footer pt-0 p-3"),
        )

    class Meta:
        model = TimeSlot
        widgets = {
          'start': DateTimePickerInput(),
          'end': DateTimePickerInput(),
        }
        fields = (
            'user',
            'phase',
            'slot_type',
            # 'deliveryRole',
            'is_onsite',
            'start',
            'end',
            )


class DeliveryTimeSlotModalForm(forms.ModelForm):
    phase = forms.ModelChoiceField(
        queryset=Phase.objects.filter(),
        widget=autocomplete.ModelSelect2(
            url='phase-autocomplete',
            attrs={
                'data-minimum-input-length': 3,
            },),)
    
    def __init__(self, *args, **kwargs):
        if 'phase' in kwargs:
            phase = kwargs.pop('phase')
        else:
            phase = None
        if 'job' in kwargs:
            job = kwargs.pop('job')
        else:
            job = None
        if 'user' in kwargs:
            user = kwargs.pop('user')
        else:
            user = None
        if 'start' in kwargs:
            start = kwargs.pop('start')
        else:
            start = None
        if 'end' in kwargs:
            end = kwargs.pop('end')
        else:
            end = None
        super(DeliveryTimeSlotModalForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        for fieldname in self.fields:
            self.fields[fieldname].help_text = None
        self.fields['user'].widget = forms.HiddenInput()
        if user:
            self.fields['user'].initial = user
            self.fields['user'].disabled = user
        
        self.fields['slot_type'].widget = forms.HiddenInput()
        self.fields['slot_type'].initial = TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.DELIVERY)
        self.fields['slot_type'].disabled = True

        if phase:
            self.fields['phase'].disabled = True
            self.fields['phase'].initial = phase
        else:
            if job:
                phases = Phase.objects.filter(job=job)
                from pprint import pprint
                pprint(phases)
                self.fields['phase'].widget = autocomplete.ModelSelect2()
                self.fields['phase'].queryset = phases
        
        if self.instance.phase:
            delete_button = StrictButton("Delete", type="button", 
                data_url=reverse('job_slot_delete', kwargs={"slug":self.instance.phase.job.slug, "pk":self.instance.pk}),
                css_class="btn js-load-modal-form btn-outline-phoenix-danger me-auto mb-0")

            goto_button = HTML("<a href='"+reverse('phase_detail', kwargs={"job_slug":self.instance.phase.job.slug, "slug":self.instance.phase.slug})+"' class='btn btn-outline-phoenix-secondary'>Goto Phase</a>")
        else:
            goto_button = None
            delete_button = None

        self.fields['start'].widget = DateTimePickerInput()
        if start:
            self.fields['start'].initial = start

        self.fields['end'].widget = DateTimePickerInput()
        if end:
            self.fields['end'].initial = end
            
        self.helper.layout = Layout(
            Div(
                Row(
                    Field('phase', style="width: 100%;"),
                    Field('user', style="width: 100%;"),
                    ),
                Row(
                    Column(Div(FloatingField('deliveryRole'),
                            css_class="input-group input-group-dynamic")),
                    Column(Div(Field('is_onsite'),
                            css_class="input-group input-group-dynamic")),
                    ),
                Row(
                    Column(Div(Field('start'),
                            css_class="input-group input-group-dynamic")),
                    Column(Div(Field('end'),
                            css_class="input-group input-group-dynamic")),
                    ),
                css_class='card-body p-3'),
            Div(
                Div(delete_button,
                    goto_button,
                    StrictButton("Save", type="submit", 
                        css_class="btn btn-outline-phoenix-success ms-auto mb-0"),
                    css_class="button-row d-flex"),
                css_class="card-footer pt-0 p-3"),
        )

    class Meta:
        model = TimeSlot
        widgets = {
          'start': DateTimePickerInput(),
          'end': DateTimePickerInput(),
        }
        fields = (
            'user',
            'phase',
            'slot_type',
            'deliveryRole',
            'is_onsite',
            'start',
            'end',
        )

class ChangeTimeSlotDateModalForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(ChangeTimeSlotDateModalForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        for fieldname in self.fields:
            self.fields[fieldname].help_text = None
        # if self.instance.phase:
        #     delete_button = StrictButton("Delete", type="button", 
        #         data_url=reverse('job_slot_delete', kwargs={"slug":self.instance.phase.job.slug, "pk":self.instance.pk}),
        #         css_class="btn btn-danger js-load-modal-form btn-outline-danger me-auto mb-0")
        # else:
        #     delete_button = None
        self.fields['user'].widget = forms.HiddenInput()
        self.fields['start'].widget = DateTimePickerInput()
        self.fields['end'].widget = DateTimePickerInput()
        self.helper.layout = Layout(
            Field('user', type="hidden"),
            Div(
                Row(
                    Column(Div(Field('start'),
                            css_class="input-group input-group-dynamic")),
                    Column(Div(Field('end'),
                            css_class="input-group input-group-dynamic")),
                ),
                css_class='card-body p-3'),
            Div(
                Div(
                    # delete_button,
                    StrictButton("Save", type="submit", 
                        css_class="btn btn-outline-phoenix-success ms-auto mb-0"),
                    css_class="button-row d-flex"),
                css_class="card-footer pt-0 p-3"),
        )

    class Meta:
        model = TimeSlot
        widgets = {
          'start': DateTimePickerInput(),
          'end': DateTimePickerInput(),
        }
        fields = (
            'user',
            'start',
            'end',
        )


class JobForm(forms.ModelForm):
    account_manager = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        widget=autocomplete.ModelSelect2(url='user-autocomplete',
                                         attrs={
                                             'data-minimum-input-length': 3,
                                         },),)
    
    dep_account_manager = forms.ModelChoiceField(
        required=False,
        queryset=User.objects.filter(is_active=True),
        widget=autocomplete.ModelSelect2(url='user-autocomplete',
                                         attrs={
                                             'data-minimum-input-length': 3,
                                         },),)
    
    client = forms.ModelChoiceField(
        queryset=Client.objects.filter(account_managers__isnull=False),
        widget=autocomplete.ModelSelect2(),)

    overview = forms.CharField(
        required=False,
        widget=forms.Textarea(
        attrs={
            'class': "tinymce",
            'data-tinymce': '{"height":"15rem","placeholder":"Write a description here..."}',
            'rows': 5,
        },),
    )    

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')  # To get request.user. Do not use kwargs.pop('user', None) due to potential security hole
        super(JobForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields['unit'].queryset = OrganisationalUnit.objects.filter(
            pk__in=self.user.unit_memberships.filter(role__in=UnitRoles.get_roles_with_permission('jobtracker.can_add_job')).values_list('unit').distinct())
        self.fields['title'].label = ""
        self.fields['client'].label = ""
        self.fields['external_id'].label = ""
        self.fields['unit'].label = ""
        self.fields['overview'].label = ""  
        self.fields['revenue'].label = ""  
        self.fields['account_manager'].label = ""  
        self.fields['dep_account_manager'].label = ""  
        self.fields['desired_start_date'].label = ""  
        self.fields['desired_delivery_date'].label = ""  

    class Meta:
        model = Job
        widgets = {
          'desired_start_date': DatePickerInput(),
          'desired_delivery_date': DatePickerInput(),
          'unit': autocomplete.ModelSelect2(),
        }
        fields = [
            "unit", 
            "client", 
            "title", 
            "external_id",
            "revenue", 
            "overview", 
            "account_manager", 
            "dep_account_manager",
            "desired_start_date",
            "desired_delivery_date",
        ]

class PhaseForm(forms.ModelForm):

    description = forms.CharField(required=False, widget=forms.Textarea(
        attrs={
            'class': "tinymce",
            'data-tinymce': '{"height":"15rem","placeholder":"Write a description here..."}',
            'rows': 5,
        },),
    )    

    def __init__(self, *args, **kwargs):
        job=None
        if 'job' in kwargs:
            job = kwargs.pop('job')
        super(PhaseForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        if job:
            self.fields['phase_number'].initial = Phase.objects.filter(job=job).count() + 1
        self.fields['delivery_hours'].label = False
        self.fields['reporting_hours'].label = False
        self.fields['mgmt_hours'].label = False
        self.fields['qa_hours'].label = False
        self.fields['oversight_hours'].label = False
        self.fields['debrief_hours'].label = False
        self.fields['contingency_hours'].label = False
        self.fields['contingency_hours'].css_class = "mb-0"
        self.fields['other_hours'].label = False

        self.fields['desired_start_date'].widget = DatePickerInput()
        self.fields['due_to_techqa_set'].widget = DatePickerInput()
        self.fields['due_to_presqa_set'].widget = DatePickerInput()
        self.fields['desired_delivery_date'].widget = DatePickerInput()

    class Meta:
        model = Phase
        widgets = {
          'desired_start_date': DatePickerInput(),
          'due_to_techqa_set': DatePickerInput(),
          'due_to_presqa_set': DatePickerInput(),
          'desired_delivery_date': DatePickerInput(),
        }
        fields = [
            "phase_number",
            "title",
            "service",
            "description",
            "test_target",
            "comm_reqs",
            "delivery_hours",
            "reporting_hours",
            "mgmt_hours",
            "qa_hours",
            "oversight_hours",
            "debrief_hours",
            "contingency_hours",
            "other_hours",
            "desired_start_date",
            "due_to_techqa_set",
            "due_to_presqa_set",
            "desired_delivery_date",

            "is_testing_onsite",
            "is_reporting_onsite",
            "number_of_reports",
            "report_to_be_left_on_client_site",
            "location",
            "restrictions",
            "scheduling_requirements",
            "prerequisites",
            ]
        

class ScopeInlineForm(forms.ModelForm):

    overview = forms.CharField(
        required=False,
        label="",
        widget=forms.Textarea(
        attrs={
            'class': "tinymce",
            'data-tinymce': '{"height":"15rem","placeholder":"Write a description here..."}',
            'rows': 5,
        },),
    )

    def __init__(self, *args, **kwargs):
        super(ScopeInlineForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)

    class Meta:
        model = Job
        fields = [
            "overview", 
            "additional_kit_required", 
            "kit_sourced_by_client", 
            "additional_kit_info",  
            "is_restricted", 
            "restricted_detail",  
            "bespoke_project", 
            "report_to_third_party",  
            "is_time_limited", 
            "retest_included",  
            "technically_complex_test",  
            "high_risk", 
            "reasons_for_high_risk",  
        ]
        

class PhaseDeliverInlineForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(PhaseDeliverInlineForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields['linkDeliverable'].label = False
        self.fields['linkTechData'].label = False
        self.fields['linkReportData'].label = False

    class Meta:
        model = Phase
        fields = [
            "linkDeliverable", 
            "linkTechData", 
            "linkReportData", 
        ]

class PhaseScopeFeedbackInlineForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(PhaseScopeFeedbackInlineForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields['feedback_scope_correct'].label = False

    class Meta:
        model = Phase
        fields = [
            # "feedback_scope",  
            "feedback_scope_correct", 
        ]
        

class PhaseTechQAInlineForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(PhaseTechQAInlineForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields['techqa_report_rating'].label = False
        self.fields['techqa_report_rating'].required = False

    class Meta:
        model = Phase
        fields = [
            "techqa_report_rating", 
        ]

class PhasePresQAInlineForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(PhasePresQAInlineForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields['presqa_report_rating'].label = False

    class Meta:
        model = Phase
        fields = [
            "presqa_report_rating", 
        ]

class ScopeForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(ScopeForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
                Div(
                    Div(HTML('<h5>General Details</h5>'), 
                        css_class='card-header'),
                    Div(
                        Row(
                            Div(FloatingField('overview'),
                                css_class="input-group input-group-dynamic"),
                        css_class="mx-3"),
                        css_class='card-body pt-3 px-0 pb-0'),
                    css_class="card mb-3"),

                Div(
                    Div(HTML('<h5>Kit Requirements</h5>'), 
                        css_class='card-header'),
                    Div(Row(
                            Column(Div(Field('additional_kit_required'),
                                    css_class="input-group input-group-dynamic")),
                            Column(Div(Field('kit_sourced_by_client'),
                                    css_class="input-group input-group-dynamic")),
                        ),
                        Row(
                            Div(FloatingField('additional_kit_info'),
                                css_class="input-group input-group-dynamic"),
                        css_class="mx-3"),
                        css_class='card-body pt-3 px-0 pb-0'),
                    css_class="card mb-3"),

                Div(
                    Div(HTML('<h5>Restrictions</h5>'), 
                        css_class='card-header'),
                    Div(Row(
                            Column(Div(Field('is_restricted'),
                                    css_class="input-group input-group-dynamic")),
                            Column(Div(Field('restricted_detail'),
                                    css_class="input-group input-group-dynamic")),
                        ),
                        css_class='card-body pt-3 px-0 pb-0'),
                    css_class="card mb-3"),

                Div(
                    Div(HTML('<h5>Special Flags</h5>'), 
                        css_class='card-header'),
                    Div(Row(
                            Column(Div(Field('bespoke_project'),
                                    css_class="input-group input-group-dynamic")),
                            Column(Div(Field('report_to_third_party'),
                                    css_class="input-group input-group-dynamic")),
                            Column(Div(Field('is_time_limited'),
                                    css_class="input-group input-group-dynamic")),
                            Column(Div(Field('retest_included'),
                                    css_class="input-group input-group-dynamic")),
                        ),
                        Row(
                            Column(Div(Field('technically_complex_test'),
                                    css_class="input-group input-group-dynamic")),
                            Column(Div(Field('high_risk'),
                                    css_class="input-group input-group-dynamic")),
                        ),
                        Row(
                            Div(FloatingField('reasons_for_high_risk'),
                                css_class="input-group input-group-dynamic"),
                        css_class="mx-3"),
                        css_class='card-body pt-3 px-0 pb-0'),
                    css_class="card mb-3"),

            Div(StrictButton("Save", type="submit", 
                    css_class="btn btn-outline-phoenix-success ms-auto mb-0"),
                css_class="button-row d-flex mt-4"),
        )

    class Meta:
        model = Job
        fields = [
            "overview", 
            "additional_kit_required", 
            "kit_sourced_by_client", 
            "additional_kit_info",  
            "is_restricted", 
            "restricted_detail",  
            "bespoke_project", 
            "report_to_third_party",  
            "is_time_limited", 
            "retest_included",  
            "technically_complex_test",  
            "high_risk", 
            "reasons_for_high_risk",  
        ]


class ClientForm(forms.ModelForm):
    specific_requirements = forms.CharField(
        required=False,
        widget=forms.Textarea(
        attrs={
            'class': "tinymce",
            'data-tinymce': '{"height":"15rem","placeholder":"Write an special requirements of this team here..."}',
            'rows': 5,
        },),
    )    
    account_managers = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True),
        widget=autocomplete.ModelSelect2Multiple(url='user-autocomplete',
                                         attrs={
                                             'data-minimum-input-length': 3,
                                         },),)
    
    tech_account_managers = forms.ModelMultipleChoiceField(
        required=False,
        queryset=User.objects.filter(is_active=True),
        widget=autocomplete.ModelSelect2Multiple(url='user-autocomplete',
                                         attrs={
                                             'data-minimum-input-length': 3,
                                         },),)

    def __init__(self, *args, **kwargs):
        super(ClientForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields['name'].label = False
        self.fields['short_name'].label = False
        self.fields['specific_requirements'].label = False
        self.fields['account_managers'].label = False
        self.fields['tech_account_managers'].label = False

    class Meta:
        model = Client
        fields = ["name", "short_name", "specific_requirements", "account_managers", "tech_account_managers"]


class ClientContactForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(ClientContactForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields['salutation'].label = False
        self.fields['first_name'].label = False
        self.fields['last_name'].label = False

        self.fields['jobtitle'].label = False
        self.fields['department'].label = False

        self.fields['phone'].label = False
        self.fields['mobile'].label = False
        self.fields['email'].label = False

    class Meta:
        model = Contact
        fields = [
            "salutation", 
            "first_name", 
            "last_name",
            "jobtitle", 
            "department", 
            "phone", 
            "mobile", 
            "email",
        ]


class OrganisationalUnitMemberForm(forms.ModelForm):
    member = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        widget=autocomplete.ModelSelect2(url='user-autocomplete',
                                         attrs={
                                             'data-minimum-input-length': 3,
                                         },),)

    def __init__(self, *args, **kwargs):
        org_unit = kwargs.pop('org_unit', None)
        super(OrganisationalUnitMemberForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field('member', style="width: 100%;"),
        )
        # self.fields['name'].label = False
        # self.fields['description'].label = False
        # self.fields['special_requirements'].label = False
        self.fields['member'].label = False

    class Meta:
        model = OrganisationalUnitMember
        fields = ["member", 
                ]


class OrganisationalUnitForm(forms.ModelForm):
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(
        attrs={
            'class': "tinymce",
            'data-tinymce': '{"height":"15rem","placeholder":"Write a description here..."}',
            'rows': 5,
        },),
    )    
    special_requirements = forms.CharField(
        required=False,
        widget=forms.Textarea(
        attrs={
            'class': "tinymce",
            'data-tinymce': '{"height":"15rem","placeholder":"Write an special requirements of this team here..."}',
            'rows': 5,
        },),
    )    
    lead = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        widget=autocomplete.ModelSelect2(url='user-autocomplete',
                                         attrs={
                                             'data-minimum-input-length': 3,
                                         },),)

    def __init__(self, *args, **kwargs):
        super(OrganisationalUnitForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields['name'].label = False
        self.fields['description'].label = False
        self.fields['special_requirements'].label = False
        self.fields['lead'].label = False

    class Meta:
        model = OrganisationalUnit
        fields = ["name", 
                  "description", 
                  "lead",
                  "image", 
                  "special_requirements", 
                  "approval_required", 
                  "targetProfit",
                  "businessHours_startTime", 
                  "businessHours_endTime", 
                  "businessHours_days"
                ]
        widgets = {
          'businessHours_days': forms.TextInput(),
          'businessHours_startTime': TimePickerInput(),
          'businessHours_endTime': TimePickerInput(),
        }


class ServiceForm(forms.ModelForm):
    owners = forms.ModelMultipleChoiceField(
        required=False,
        queryset=User.objects.filter(is_active=True),
        widget=autocomplete.ModelSelect2Multiple(url='user-autocomplete',
                                         attrs={
                                             'data-minimum-input-length': 3,
                                         },),)
    
    skillsRequired = forms.ModelMultipleChoiceField(
        required=False,
        queryset=Skill.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(),)
    
    skillsDesired = forms.ModelMultipleChoiceField(
        required=False,
        queryset=Skill.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(),)

    def __init__(self, *args, **kwargs):
        super(ServiceForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields['name'].label = False
        self.fields['owners'].label = False

        self.fields['skillsRequired'].label = False
        self.fields['skillsDesired'].label = False
        

    class Meta:
        model = Service
        fields = ["name", "owners", "skillsRequired", "skillsDesired"]


class WFTaskForm(forms.ModelForm): 
    status = forms.IntegerField(
        widget=forms.Select(),)

    def __init__(self, *args, **kwargs):
        status_choices = kwargs.pop('status_choices')
        if 'applied_model' in kwargs:
            _ = kwargs.pop('applied_model')
        super(WFTaskForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)

        self.fields['status'].widget.choices = status_choices
        self.fields['status'].label = False
        self.fields['task'].label = False

    class Meta:
        model = WorkflowTask
        fields = ["status", "task"]


class SkillForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(SkillForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields['name'].label = False

    class Meta:
        model = Skill
        fields = ["name"]


class SkillCatForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(SkillCatForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields['name'].label = False

    class Meta:
        model = SkillCategory
        fields = ["name"]