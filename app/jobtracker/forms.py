from django import forms
from django.urls import reverse
from .models import (
    Contact,
    FrameworkAgreement,
    Job,
    JobSupportTeamRole,
    Qualification,
    QualificationRecord,
    AwardingBody,
    Feedback,
    TimeSlot,
    TimeSlotType,
    TimeSlotComment,
    Client,
    Phase,
    Project,
    OrganisationalUnit,
    OrganisationalUnitMember,
    Skill,
    Service,
    WorkflowTask,
    SkillCategory,
    BillingCode,
    OrganisationalUnitRole,
)
from chaotica_utils.models import Note, User
from .enums import DefaultTimeSlotTypes, JobStatuses, PhaseStatuses
from crispy_forms.helper import FormHelper
from crispy_forms.bootstrap import StrictButton
from crispy_forms.layout import Layout, Row, Column, Field, Div, HTML, Submit
from crispy_bootstrap5.bootstrap5 import FloatingField
from dal import autocomplete, forward
from chaotica_utils.enums import UnitRoles
from bootstrap_datepicker_plus.widgets import (
    TimePickerInput,
    DatePickerInput,
    DateTimePickerInput,
)


class SchedulerFilter(forms.Form):
    skills_specialist = forms.ModelMultipleChoiceField(
        required=False,
        label="Specialist",
        queryset=Skill.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(),
    )
    skills_can_do_alone = forms.ModelMultipleChoiceField(
        required=False,
        label="Independent",
        queryset=Skill.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(),
    )
    skills_can_do_support = forms.ModelMultipleChoiceField(
        required=False,
        label="Require Support",
        queryset=Skill.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(),
    )

    services = forms.ModelMultipleChoiceField(
        required=False,
        queryset=Service.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(),
    )

    org_units = forms.ModelMultipleChoiceField(
        required=False,
        queryset=OrganisationalUnit.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(),
    )

    org_unit_roles = forms.ModelMultipleChoiceField(
        required=False,
        queryset=OrganisationalUnitRole.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(),
    )

    from_date = forms.DateField(
        required=False,
        widget=DatePickerInput(),
    )
    to_date = forms.DateField(
        required=False,
        widget=DatePickerInput(),
    )

    users = forms.ModelMultipleChoiceField(
        required=False,
        queryset=User.objects.filter(),
        widget=autocomplete.ModelSelect2Multiple(
            url="user-autocomplete",
            attrs={
                "data-minimum-input-length": 3,
            },
        ),
    )

    include_user = forms.ModelMultipleChoiceField(
        required=False,
        queryset=User.objects.filter(),
        widget=autocomplete.ModelSelect2Multiple(
            url="user-autocomplete",
            attrs={
                "data-minimum-input-length": 3,
            },
        ),
    )
    

    jobs = forms.ModelMultipleChoiceField(
        required=False,
        queryset=Job.objects.filter(),
        widget=autocomplete.ModelSelect2Multiple(
            url="job-autocomplete",
            attrs={
                "data-minimum-input-length": 3,
            },
        ),
    )

    phases = forms.ModelMultipleChoiceField(
        required=False,
        queryset=Phase.objects.filter(),
        widget=autocomplete.ModelSelect2Multiple(
            url="phase-autocomplete",
            attrs={
                "data-minimum-input-length": 3,
            },
        ),
    )

    show_inactive_users = forms.BooleanField(
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super(SchedulerFilter, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_method = "get"
        self.helper.form_class = "form-inline"
        self.helper.layout = Layout(
            Div(
                HTML('<h5 class="setting-panel-item-title">Date Range</h5>'),
                Row(
                    Column(
                        Field(
                            "from_date",
                        ),
                        css_class="me-3",
                    ),
                    Column(
                        Field(
                            "to_date",
                        ),
                    ),
                ),
                css_class="setting-panel-item",
            ),
            Div(
                HTML('<h5 class="setting-panel-item-title">Users</h5>'),
                Row(
                    Field("show_inactive_users",),
                    Field("users", style="width: 100%;"),
                ),
                Row(
                    Column(
                    Field("org_units", style="width: 100%;"),
                    ),
                    Column(
                    Field("org_unit_roles", style="width: 100%;"),
                    ),
                ),
                css_class="setting-panel-item",
            ),
            Div(
                HTML('<h5 class="setting-panel-item-title">Job</h5>'),
                Row(
                    Field("jobs", style="width: 100%;"),
                    Field("phases", style="width: 100%;"),
                ),
                css_class="setting-panel-item",
            ),
            Div(
                HTML('<h5 class="setting-panel-item-title">Skills</h5>'),
                Row(
                    Field("skills_specialist", css_class="extra", style="width: 100%;"),
                    Field(
                        "skills_can_do_alone", css_class="extra", style="width: 100%;"
                    ),
                    Field(
                        "skills_can_do_support", css_class="extra", style="width: 100%;"
                    ),
                ),
                css_class="setting-panel-item",
            ),
            Div(
                HTML('<h5 class="setting-panel-item-title">Service</h5>'),
                Row(
                    Field("services", style="width: 100%;"),
                ),
                css_class="setting-panel-item",
            ),
            Row(
                Submit(
                    "apply", "Apply", css_class="btn-phoenix-success d-grid mb-3 mt-5"
                ),
            ),
        )

    class Meta:
        fields = (
            "skills_specialist",
            "skills_can_do_alone",
            "skills_can_do_support",
            "show_inactive_users",
            "users",
            "include_user",
            "services",
            "jobs",
            "phases",
            "org_units",
            "org_unit_roles",
            "from_date",
            "to_date",
        )


class AssignJobFramework(forms.ModelForm):
    associated_framework = forms.ModelChoiceField(
        required=False,
        queryset=FrameworkAgreement.objects.all(),
    )

    def __init__(self, *args, **kwargs):
        super(AssignJobFramework, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields["associated_framework"].queryset = (
            FrameworkAgreement.objects.filter(client=self.instance.client)
        )
        self.helper.layout = Layout(
            Div(
                Row(
                    Div(
                        Field("associated_framework"),
                        css_class="input-group input-group-dynamic",
                    )
                ),
                css_class="modal-body pt-3",
            ),
            Div(
                Div(
                    StrictButton(
                        "Save",
                        type="submit",
                        css_class="btn btn-outline-success ms-auto mb-0",
                    ),
                    css_class="button-row d-flex",
                ),
                css_class="modal-footer",
            ),
        )

    class Meta:
        model = Job
        fields = ("associated_framework",)


class AssignJobBillingCode(forms.ModelForm):
    charge_codes = forms.ModelMultipleChoiceField(
        required=False,
        queryset=BillingCode.objects.filter(),
        widget=autocomplete.ModelSelect2Multiple(
            url="job_autocomplete_billingcodes",
            attrs={"data-html": True},
            forward=["slug"],
        ),
    )

    def __init__(self, *args, **kwargs):
        super(AssignJobBillingCode, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields["charge_codes"].widget.forward = [
            forward.Const(str(self.instance.slug), "slug"),
        ]
        self.helper.layout = Layout(
            Div(
                Row(
                    Div(
                        Field("charge_codes", style="width: 100%;"),
                        css_class="input-group input-group-dynamic",
                    )
                ),
                css_class="modal-body pt-3",
            ),
            Div(
                Div(
                    StrictButton(
                        "Save",
                        type="submit",
                        css_class="btn btn-outline-success ms-auto mb-0",
                    ),
                    css_class="button-row d-flex",
                ),
                css_class="modal-footer",
            ),
        )

    class Meta:
        model = Job
        fields = ("charge_codes",)


class AssignContact(forms.Form):
    contact = forms.ModelChoiceField(
        required=False,
        queryset=Contact.objects.none(),
    )

    def __init__(self, *args, **kwargs):
        contacts = None
        if "contacts" in kwargs:
            contacts = kwargs.pop("contacts")
        super(AssignContact, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        if contacts:
            self.fields["contact"].queryset = contacts
        self.helper.layout = Layout(
            Div(
                Row(Div(Field("contact"), css_class="input-group input-group-dynamic")),
                css_class="modal-body pt-3",
            ),
            Div(
                Div(
                    StrictButton(
                        "Save",
                        type="submit",
                        css_class="btn btn-outline-success ms-auto mb-0",
                    ),
                    css_class="button-row d-flex",
                ),
                css_class="modal-footer",
            ),
        )

    class Meta:
        fields = ("contact",)


class AssignMultipleContacts(forms.Form):
    contacts = forms.ModelMultipleChoiceField(
        required=False,
        queryset=Contact.objects.all(),
    )

    def __init__(self, *args, **kwargs):
        if "contacts" in kwargs:
            contacts = kwargs.pop("contacts")
        super(AssignMultipleContacts, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        if contacts:
            self.fields["contacts"].queryset = contacts
        self.helper.layout = Layout(
            Div(
                Row(
                    Div(Field("contacts"), css_class="input-group input-group-dynamic")
                ),
                css_class="modal-body pt-3",
            ),
            Div(
                Div(
                    StrictButton(
                        "Save",
                        type="submit",
                        css_class="btn btn-outline-success ms-auto mb-0",
                    ),
                    css_class="button-row d-flex",
                ),
                css_class="modal-footer",
            ),
        )


class AssignUserField(forms.Form):
    user = forms.ModelMultipleChoiceField(
        required=False,
        queryset=User.objects.filter(is_active=True),
        widget=autocomplete.ModelSelect2Multiple(
            url="user-autocomplete",
            attrs={
                "data-minimum-input-length": 3,
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        super(AssignUserField, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields["user"].help_text = None
        self.fields["user"].label = False
        self.helper.layout = Layout(
            Field("user", style="width: 100%;"),
            StrictButton(
                "Add",
                id="addUserToResource",
                css_class="btn btn-outline-success",
            ),
        )


class AssignUser(forms.Form):
    user = forms.ModelChoiceField(
        required=False,
        queryset=User.objects.filter(is_active=True),
        widget=autocomplete.ModelSelect2(
            url="user-autocomplete",
            attrs={
                "data-minimum-input-length": 3,
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        if "users" in kwargs:
            users = kwargs.pop("users")
        super(AssignUser, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        if users:
            self.fields["user"].queryset = users
        self.fields["user"].help_text = None
        self.fields["user"].label = None
        self.helper.form_show_labels = False
        self.helper.layout = Layout(
            Div(
                Row(
                    Field("user", style="width: 100%;"),
                ),
                css_class="modal-body p-3",
            ),
            Div(
                Div(
                    StrictButton(
                        "Save",
                        type="submit",
                        css_class="btn btn-outline-success ms-auto mb-0",
                    ),
                    css_class="button-row d-flex",
                ),
                css_class="modal-footer",
            ),
        )


class AssignMultipleUser(forms.Form):
    users = forms.ModelMultipleChoiceField(
        required=False,
        queryset=User.objects.filter(is_active=True),
        widget=autocomplete.ModelSelect2Multiple(
            url="user-autocomplete",
            attrs={
                "data-minimum-input-length": 3,
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        if "users" in kwargs:
            users = kwargs.pop("users")
        super(AssignMultipleUser, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        if users:
            self.fields["users"].queryset = users
        self.helper.layout = Layout(
            Div(
                Row(
                    Field("users", style="width: 100%;"),
                ),
                css_class="modal-body pt-3",
            ),
            Div(
                Div(
                    StrictButton(
                        "Save",
                        type="submit",
                        css_class="btn btn-outline-success ms-auto mb-0",
                    ),
                    css_class="button-row d-flex",
                ),
                css_class="modal-footer",
            ),
        )


##########################
# Add Note form
##########################
class AddNote(forms.ModelForm):
    content = forms.CharField()

    def __init__(self, *args, **kwargs):
        super(AddNote, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields["content"].help_text = None
        self.fields["content"].label = None
        self.helper.form_show_labels = False

    class Meta:
        model = Note
        fields = ("content",)


##########################
# Add Feedback form
##########################
class FeedbackForm(forms.ModelForm):
    body = forms.CharField()

    def __init__(self, *args, **kwargs):
        super(FeedbackForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields["body"].help_text = None
        self.fields["body"].label = None
        self.helper.form_tag = False
        self.helper.form_show_labels = False

    class Meta:
        model = Feedback
        fields = ("body",)


class CommentTimeSlotModalForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        start = None
        if "start" in kwargs:
            start = kwargs.pop("start")
        end = None
        if "end" in kwargs:
            end = kwargs.pop("end")
        resource = None
        if "resource" in kwargs:
            resource = kwargs.pop("resource")

        super(CommentTimeSlotModalForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        for fieldname in self.fields:
            self.fields[fieldname].help_text = None
        if self.instance.pk:
            delete_button = StrictButton(
                "Delete",
                type="button",
                data_url=reverse(
                    "delete_scheduler_slot_comment", kwargs={"pk": self.instance.pk}
                ),
                css_class="btn js-load-modal-form btn-outline-danger me-auto mb-0",
            )
        else:
            delete_button = None
        self.fields["user"].widget = forms.HiddenInput()
        self.fields["user"].disabled = True
        self.fields["start"].widget = DateTimePickerInput()
        self.fields["end"].widget = DateTimePickerInput()
        if not self.instance.pk:
            self.fields["start"].initial = start
            self.fields["end"].initial = end
            self.fields["user"].initial = resource
        self.helper.layout = Layout(
            Field("user", style="width: 100%;"),
            Div(
                Row(
                    Column(
                        Div(
                            FloatingField("comment"),
                        )
                    ),
                ),
                Row(
                    Column(
                        Div(Field("start"), css_class="input-group input-group-dynamic")
                    ),
                    Column(
                        Div(Field("end"), css_class="input-group input-group-dynamic")
                    ),
                ),
                css_class="card-body p-3",
            ),
            Div(
                Div(
                    delete_button,
                    StrictButton(
                        "Save",
                        type="submit",
                        css_class="btn btn-outline-success ms-auto mb-0",
                    ),
                    css_class="button-row d-flex",
                ),
                css_class="card-footer pt-0 p-3",
            ),
        )

    class Meta:
        model = TimeSlotComment
        widgets = {
            "start": DateTimePickerInput(),
            "end": DateTimePickerInput(),
        }
        fields = (
            "user",
            "comment",
            "start",
            "end",
        )


class NonDeliveryTimeSlotModalForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        start = None
        if "start" in kwargs:
            start = kwargs.pop("start")
        end = None
        if "end" in kwargs:
            end = kwargs.pop("end")
        resource = None
        if "resource" in kwargs:
            resource = kwargs.pop("resource")

        super(NonDeliveryTimeSlotModalForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        for fieldname in self.fields:
            self.fields[fieldname].help_text = None
        if self.instance.pk:
            delete_button = StrictButton(
                "Delete",
                type="button",
                data_url=reverse(
                    "delete_scheduler_slot", kwargs={"pk": self.instance.pk}
                ),
                css_class="btn js-load-modal-form btn-outline-danger me-auto mb-0",
            )
        else:
            delete_button = None
        self.fields["user"].widget = forms.HiddenInput()
        self.fields["user"].disabled = True
        self.fields["phase"].disabled = True
        self.fields["start"].widget = DateTimePickerInput()
        self.fields["end"].widget = DateTimePickerInput()
        if not self.instance.pk:
            self.fields["start"].initial = start
            self.fields["end"].initial = end
            self.fields["user"].initial = resource
        self.fields["slot_type"].queryset = TimeSlotType.objects.filter(
            is_assignable=True
        )
        self.helper.layout = Layout(
            Field("user", style="width: 100%;"),
            Field("phase", type="hidden"),
            Div(
                Row(
                    Column(
                        Div(
                            FloatingField("slot_type"),
                            css_class="input-group input-group-dynamic",
                        )
                    ),
                ),
                Row(
                    Column(
                        Div(Field("start"), css_class="input-group input-group-dynamic")
                    ),
                    Column(
                        Div(Field("end"), css_class="input-group input-group-dynamic")
                    ),
                ),
                css_class="card-body p-3",
            ),
            Div(
                Div(
                    delete_button,
                    StrictButton(
                        "Save",
                        type="submit",
                        css_class="btn btn-outline-success ms-auto mb-0",
                    ),
                    css_class="button-row d-flex",
                ),
                css_class="card-footer pt-0 p-3",
            ),
        )

    class Meta:
        model = TimeSlot
        widgets = {
            "start": DateTimePickerInput(),
            "end": DateTimePickerInput(),
        }
        fields = (
            "user",
            "phase",
            "slot_type",
            # 'deliveryRole',
            "is_onsite",
            "start",
            "end",
        )


class DeliveryTimeSlotModalForm(forms.ModelForm):
    phase = forms.ModelChoiceField(
        queryset=Phase.objects.filter(),
        widget=autocomplete.ModelSelect2(
            url="phase-autocomplete",
            attrs={
                "data-minimum-input-length": 3,
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        if "phase" in kwargs:
            phase = kwargs.pop("phase")
        else:
            phase = None
        if "job" in kwargs:
            job = kwargs.pop("job")
        else:
            job = None
        if "user" in kwargs:
            user = kwargs.pop("user")
        else:
            user = None
        if "start" in kwargs:
            start = kwargs.pop("start")
        else:
            start = None
        if "end" in kwargs:
            end = kwargs.pop("end")
        else:
            end = None
        if "slug" in kwargs:
            slug = kwargs.pop("slug")
        else:
            slug = None
        super(DeliveryTimeSlotModalForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        for fieldname in self.fields:
            self.fields[fieldname].help_text = None
        self.fields["user"].widget = forms.HiddenInput()
        if user:
            self.fields["user"].initial = user
            self.fields["user"].disabled = user

        self.fields["slot_type"].widget = forms.HiddenInput()
        self.fields["slot_type"].initial = TimeSlotType.get_builtin_object(
            DefaultTimeSlotTypes.DELIVERY
        )
        self.fields["slot_type"].disabled = True

        if phase:
            self.fields["phase"].disabled = True
            self.fields["phase"].initial = phase
        else:
            if job:
                phases = Phase.objects.filter(job=job)
                self.fields["phase"].widget = autocomplete.ModelSelect2()
                self.fields["phase"].queryset = phases

        if self.instance.phase:
            delete_button = StrictButton(
                "Delete",
                type="button",
                data_url=reverse(
                    "job_slot_delete",
                    kwargs={
                        "slug": self.instance.phase.job.slug,
                        "pk": self.instance.pk,
                    },
                ),
                css_class="btn js-load-modal-form btn-outline-danger me-auto mb-0",
            )

            goto_button = HTML(
                "<a href='"
                + reverse(
                    "phase_detail",
                    kwargs={
                        "job_slug": self.instance.phase.job.slug,
                        "slug": self.instance.phase.slug,
                    },
                )
                + "' class='btn btn-outline-info'>Goto Phase</a>"
            )
        else:
            goto_button = None
            delete_button = None

        self.fields["start"].widget = DateTimePickerInput()
        if start:
            self.fields["start"].initial = start

        self.fields["end"].widget = DateTimePickerInput()
        if end:
            self.fields["end"].initial = end

        self.helper.layout = Layout(
            Div(
                Row(
                    Field("phase", style="width: 100%;"),
                    Field("user", style="width: 100%;"),
                ),
                Row(
                    Column(
                        Div(
                            FloatingField("deliveryRole"),
                            css_class="input-group input-group-dynamic",
                        )
                    ),
                    Column(
                        Div(
                            Field("is_onsite"),
                            css_class="input-group input-group-dynamic",
                        )
                    ),
                ),
                Row(
                    Column(
                        Div(Field("start"), css_class="input-group input-group-dynamic")
                    ),
                    Column(
                        Div(Field("end"), css_class="input-group input-group-dynamic")
                    ),
                ),
                css_class="card-body p-3",
            ),
            Div(
                Div(
                    delete_button,
                    goto_button,
                    StrictButton(
                        "Save",
                        type="submit",
                        css_class="btn btn-outline-success ms-auto mb-0",
                    ),
                    css_class="button-row d-flex",
                ),
                css_class="card-footer pt-0 p-3",
            ),
        )

    class Meta:
        model = TimeSlot
        widgets = {
            "start": DateTimePickerInput(),
            "end": DateTimePickerInput(),
        }
        fields = (
            "user",
            "phase",
            "slot_type",
            "deliveryRole",
            "is_onsite",
            "start",
            "end",
        )

class ProjectTimeSlotModalForm(forms.ModelForm):
    project = forms.ModelChoiceField(
        queryset=Project.objects.filter(),
        widget=autocomplete.ModelSelect2(
            url="project-autocomplete",
            attrs={
                "data-minimum-input-length": 3,
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        if "project" in kwargs:
            project = kwargs.pop("project")
        else:
            project = None
        if "user" in kwargs:
            user = kwargs.pop("user")
        else:
            user = None
        if "start" in kwargs:
            start = kwargs.pop("start")
        else:
            start = None
        if "end" in kwargs:
            end = kwargs.pop("end")
        else:
            end = None
        super(ProjectTimeSlotModalForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        for fieldname in self.fields:
            self.fields[fieldname].help_text = None
        self.fields["user"].widget = forms.HiddenInput()
        if user:
            self.fields["user"].initial = user
            self.fields["user"].disabled = user

        self.fields["slot_type"].widget = forms.HiddenInput()
        self.fields["slot_type"].initial = TimeSlotType.get_builtin_object(
            DefaultTimeSlotTypes.INTERNAL_PROJECT
        )
        self.fields["slot_type"].disabled = True

        if project:
            self.fields["project"].disabled = True
            self.fields["project"].initial = project
        else:
            projects = Project.objects.filter()
            self.fields["project"].widget = autocomplete.ModelSelect2()
            self.fields["project"].queryset = projects

        if self.instance.project:
            delete_button = StrictButton(
                "Delete",
                type="button",
                data_url=reverse(
                    "project_slot_delete",
                    kwargs={
                        "slug": self.instance.project.slug,
                        "pk": self.instance.pk,
                    },
                ),
                css_class="btn js-load-modal-form btn-outline-danger me-auto mb-0",
            )

            goto_button = HTML(
                "<a href='"
                + reverse(
                    "project_detail",
                    kwargs={
                        "slug": self.instance.project.slug,
                    },
                )
                + "' class='btn btn-outline-secondary'>Goto Project</a>"
            )
        else:
            goto_button = None
            delete_button = None

        self.fields["start"].widget = DateTimePickerInput()
        if start:
            self.fields["start"].initial = start

        self.fields["end"].widget = DateTimePickerInput()
        if end:
            self.fields["end"].initial = end

        self.helper.layout = Layout(
            Div(
                Row(
                    Field("project", style="width: 100%;"),
                    Field("user", style="width: 100%;"),
                ),
                Row(
                    Column(
                        Div(Field("start"), css_class="input-group input-group-dynamic")
                    ),
                    Column(
                        Div(Field("end"), css_class="input-group input-group-dynamic")
                    ),
                ),
                css_class="card-body p-3",
            ),
            Div(
                Div(
                    delete_button,
                    goto_button,
                    StrictButton(
                        "Save",
                        type="submit",
                        css_class="btn btn-outline-success ms-auto mb-0",
                    ),
                    css_class="button-row d-flex",
                ),
                css_class="card-footer pt-0 p-3",
            ),
        )

    class Meta:
        model = TimeSlot
        widgets = {
            "start": DateTimePickerInput(),
            "end": DateTimePickerInput(),
        }
        fields = (
            "user",
            "project",
            "slot_type",
            "start",
            "end",
        )


class ChangeTimeSlotCommentDateModalForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(ChangeTimeSlotCommentDateModalForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        for fieldname in self.fields:
            self.fields[fieldname].help_text = None
        self.fields["user"].widget = forms.HiddenInput()
        self.fields["start"].widget = DateTimePickerInput()
        self.fields["end"].widget = DateTimePickerInput()
        self.helper.layout = Layout(
            Field("user", type="hidden"),
            Div(
                Row(
                    Column(
                        Div(Field("start"), css_class="input-group input-group-dynamic")
                    ),
                    Column(
                        Div(Field("end"), css_class="input-group input-group-dynamic")
                    ),
                ),
                css_class="card-body p-3",
            ),
            Div(
                Div(
                    StrictButton(
                        "Save",
                        type="submit",
                        css_class="btn js-load-modal-form btn-outline-success ms-auto mb-0",
                    ),
                    css_class="button-row d-flex",
                ),
                css_class="card-footer pt-0 p-3",
            ),
        )

    class Meta:
        model = TimeSlotComment
        widgets = {
            "start": DateTimePickerInput(),
            "end": DateTimePickerInput(),
        }
        fields = (
            "user",
            "start",
            "end",
        )


class ChangeTimeSlotDateModalForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(ChangeTimeSlotDateModalForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        for fieldname in self.fields:
            self.fields[fieldname].help_text = None
        self.fields["user"].widget = forms.HiddenInput()
        self.fields["start"].widget = DateTimePickerInput()
        self.fields["end"].widget = DateTimePickerInput()
        self.helper.layout = Layout(
            Field("user", type="hidden"),
            Div(
                Row(
                    Column(
                        Div(Field("start"), css_class="input-group input-group-dynamic")
                    ),
                    Column(
                        Div(Field("end"), css_class="input-group input-group-dynamic")
                    ),
                ),
                css_class="card-body p-3",
            ),
            Div(
                Div(
                    StrictButton(
                        "Save",
                        type="submit",
                        css_class="btn btn-outline-success ms-auto mb-0",
                    ),
                    css_class="button-row d-flex",
                ),
                css_class="card-footer pt-0 p-3",
            ),
        )

    class Meta:
        model = TimeSlot
        widgets = {
            "start": DateTimePickerInput(),
            "end": DateTimePickerInput(),
        }
        fields = (
            "user",
            "start",
            "end",
        )


class JobForm(forms.ModelForm):
    account_manager = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        widget=autocomplete.ModelSelect2(
            url="user-autocomplete",
            attrs={
                "data-minimum-input-length": 3,
            },
        ),
    )

    indicative_services = forms.ModelMultipleChoiceField(
        required=False,
        queryset=Service.objects.filter(),
        widget=autocomplete.ModelSelect2Multiple(),
    )

    dep_account_manager = forms.ModelChoiceField(
        required=False,
        queryset=User.objects.filter(is_active=True),
        widget=autocomplete.ModelSelect2(
            url="user-autocomplete",
            attrs={
                "data-minimum-input-length": 3,
            },
        ),
    )

    client = forms.ModelChoiceField(
        queryset=Client.objects.filter(),
        widget=autocomplete.ModelSelect2(),
    )

    overview = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "tinymce",
                "data-tinymce": '{"height":"15rem","placeholder":"Write a description here..."}',
                "rows": 5,
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        # if not self.created_by:
        #     self.created_by = kwargs['initial']['created_by']
        self.user = kwargs.pop(
            "user"
        )  # To get request.user. Do not use kwargs.pop('user', None) due to potential security hole
        super(JobForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)

        # Set fields not in CHANGEABLE_FIELDS to readonly
        for field in self.fields:
            self.fields[field].label = ""
            if field not in JobStatuses.CHANGEABLE_FIELDS[self.instance.status][1]:
                self.fields[field].disabled = True

        self.fields["unit"].queryset = OrganisationalUnit.objects.filter(
            pk__in=self.user.unit_memberships.filter(
                # roles__in=UnitRoles.get_roles_with_permission("jobtracker.can_add_job")
            )
            .values_list("unit")
            .distinct()
        )

    class Meta:
        model = Job
        widgets = {
            "desired_start_date": DatePickerInput(),
            "desired_delivery_date": DatePickerInput(),
            "unit": autocomplete.ModelSelect2(),
        }
        exclude = ["created_by"]


class PhaseForm(forms.ModelForm):

    description = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "tinymce",
                "data-tinymce": '{"height":"15rem","placeholder":"Write a description here..."}',
                "rows": 5,
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        job = None
        if "job" in kwargs:
            job = kwargs.pop("job")
        super(PhaseForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        # Set fields not in CHANGEABLE_FIELDS to readonly
        for field in self.fields:
            if field.endswith("hours"):
                # Hide labels for the *hours fields as we render them nicer in a table
                self.fields[field].label = ""
            if field not in PhaseStatuses.CHANGEABLE_FIELDS[self.instance.status][1]:
                self.fields[field].disabled = True
        if job:
            self.fields["phase_number"].initial = (
                Phase.objects.filter(job=job).count() + 1
            )

        self.fields["contingency_hours"].css_class = "mb-0"
        self.fields["desired_start_date"].widget = DatePickerInput()
        self.fields["due_to_techqa_set"].widget = DatePickerInput()
        self.fields["due_to_presqa_set"].widget = DatePickerInput()
        self.fields["desired_delivery_date"].widget = DatePickerInput()

    class Meta:
        model = Phase
        widgets = {
            "desired_start_date": DatePickerInput(),
            "due_to_techqa_set": DatePickerInput(),
            "due_to_presqa_set": DatePickerInput(),
            "desired_delivery_date": DatePickerInput(),
        }
        exclude = ["slug", "phase_id", "job"]
        # fields = [
        #     "phase_number",
        #     "title",
        #     "service",
        #     "description",
        #     "test_target",
        #     "comm_reqs",
        #     "delivery_hours",
        #     "reporting_hours",
        #     "mgmt_hours",
        #     "qa_hours",
        #     "oversight_hours",
        #     "debrief_hours",
        #     "contingency_hours",
        #     "other_hours",
        #     "desired_start_date",
        #     "due_to_techqa_set",
        #     "due_to_presqa_set",
        #     "desired_delivery_date",

        #     "is_testing_onsite",
        #     "is_reporting_onsite",
        #     "number_of_reports",
        #     "report_to_be_left_on_client_site",
        #     "location",
        #     "restrictions",
        #     "scheduling_requirements",
        #     "prerequisites",
        #     ]


class ScopeInlineForm(forms.ModelForm):

    overview = forms.CharField(
        required=False,
        label="",
        widget=forms.Textarea(
            attrs={
                "class": "tinymce",
                "data-tinymce": '{"height":"15rem","placeholder":"Write a description here..."}',
                "rows": 5,
            },
        ),
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
        self.fields["linkDeliverable"].label = False
        self.fields["linkTechData"].label = False
        self.fields["linkReportData"].label = False

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
        self.fields["feedback_scope_correct"].label = False

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
        self.fields["techqa_report_rating"].label = False
        self.fields["techqa_report_rating"].required = False

    class Meta:
        model = Phase
        fields = [
            "techqa_report_rating",
        ]


class PhasePresQAInlineForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(PhasePresQAInlineForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields["presqa_report_rating"].label = False

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
                Div(HTML("<h5>General Details</h5>"), css_class="card-header"),
                Div(
                    Row(
                        Div(
                            FloatingField("overview"),
                            css_class="input-group input-group-dynamic",
                        ),
                        css_class="mx-3",
                    ),
                    css_class="card-body pt-3 px-0 pb-0",
                ),
                css_class="card mb-3",
            ),
            Div(
                Div(HTML("<h5>Kit Requirements</h5>"), css_class="card-header"),
                Div(
                    Row(
                        Column(
                            Div(
                                Field("additional_kit_required"),
                                css_class="input-group input-group-dynamic",
                            )
                        ),
                        Column(
                            Div(
                                Field("kit_sourced_by_client"),
                                css_class="input-group input-group-dynamic",
                            )
                        ),
                    ),
                    Row(
                        Div(
                            FloatingField("additional_kit_info"),
                            css_class="input-group input-group-dynamic",
                        ),
                        css_class="mx-3",
                    ),
                    css_class="card-body pt-3 px-0 pb-0",
                ),
                css_class="card mb-3",
            ),
            Div(
                Div(HTML("<h5>Restrictions</h5>"), css_class="card-header"),
                Div(
                    Row(
                        Column(
                            Div(
                                Field("is_restricted"),
                                css_class="input-group input-group-dynamic",
                            )
                        ),
                        Column(
                            Div(
                                Field("restricted_detail"),
                                css_class="input-group input-group-dynamic",
                            )
                        ),
                    ),
                    css_class="card-body pt-3 px-0 pb-0",
                ),
                css_class="card mb-3",
            ),
            Div(
                Div(HTML("<h5>Special Flags</h5>"), css_class="card-header"),
                Div(
                    Row(
                        Column(
                            Div(
                                Field("bespoke_project"),
                                css_class="input-group input-group-dynamic",
                            )
                        ),
                        Column(
                            Div(
                                Field("report_to_third_party"),
                                css_class="input-group input-group-dynamic",
                            )
                        ),
                        Column(
                            Div(
                                Field("is_time_limited"),
                                css_class="input-group input-group-dynamic",
                            )
                        ),
                        Column(
                            Div(
                                Field("retest_included"),
                                css_class="input-group input-group-dynamic",
                            )
                        ),
                    ),
                    Row(
                        Column(
                            Div(
                                Field("technically_complex_test"),
                                css_class="input-group input-group-dynamic",
                            )
                        ),
                        Column(
                            Div(
                                Field("high_risk"),
                                css_class="input-group input-group-dynamic",
                            )
                        ),
                    ),
                    Row(
                        Div(
                            FloatingField("reasons_for_high_risk"),
                            css_class="input-group input-group-dynamic",
                        ),
                        css_class="mx-3",
                    ),
                    css_class="card-body pt-3 px-0 pb-0",
                ),
                css_class="card mb-3",
            ),
            Div(
                StrictButton(
                    "Save",
                    type="submit",
                    css_class="btn btn-outline-success ms-auto mb-0",
                ),
                css_class="button-row d-flex",
            ),
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



class MergeClientForm(forms.Form):
    client_to_merge = forms.ModelChoiceField(
        queryset=Client.objects.filter(),
        required=True,
        widget=autocomplete.ModelSelect2(
            attrs={
                "data-minimum-input-length": 3,
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        super(MergeClientForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field("client_to_merge", style="width: 100%;"),
        )

    class Meta:
        fields = ("client_to_merge",)


class ClientForm(forms.ModelForm):
    specific_requirements = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "tinymce",
                "data-tinymce": '{"height":"15rem","placeholder":"Write an special requirements of this team here..."}',
                "rows": 5,
            },
        ),
    )
    specific_reporting_requirements = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "tinymce",
                "data-tinymce": '{"height":"15rem","placeholder":"Write an special requirements of this team here..."}',
                "rows": 5,
            },
        ),
    )
    account_managers = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True),
        widget=autocomplete.ModelSelect2Multiple(
            url="user-autocomplete",
            attrs={
                "data-minimum-input-length": 3,
            },
        ),
    )

    tech_account_managers = forms.ModelMultipleChoiceField(
        required=False,
        queryset=User.objects.filter(is_active=True),
        widget=autocomplete.ModelSelect2Multiple(
            url="user-autocomplete",
            attrs={
                "data-minimum-input-length": 3,
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        super(ClientForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields["name"].label = False
        self.fields["short_name"].label = False
        self.fields["specific_requirements"].label = False
        self.fields["specific_reporting_requirements"].label = False
        self.fields["account_managers"].label = False
        self.fields["tech_account_managers"].label = False

    class Meta:
        model = Client
        fields = [
            "name",
            "short_name",
            "specific_reporting_requirements",
            "specific_requirements",
            "account_managers",
            "tech_account_managers",
        ]


class ClientContactForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        client = None
        if "client" in kwargs:
            client = kwargs.pop("client")
        super(ClientContactForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields["salutation"].label = False
        self.fields["first_name"].label = False
        self.fields["last_name"].label = False

        self.fields["jobtitle"].label = False
        self.fields["department"].label = False

        self.fields["phone"].label = False
        self.fields["mobile"].label = False
        self.fields["email"].label = False

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


class ClientFrameworkForm(forms.ModelForm):
    start_date = forms.DateField(
        widget=DatePickerInput(),
    )
    end_date = forms.DateField(
        required=False,
        widget=DatePickerInput(),
    )

    def __init__(self, *args, **kwargs):
        client = None
        if "client" in kwargs:
            client = kwargs.pop("client")
        super(ClientFrameworkForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields["name"].required = True
        self.fields["start_date"].required = True
        self.fields["total_days"].required = True
        self.fields["name"].label = False
        self.fields["start_date"].label = False
        self.fields["end_date"].label = False

        self.fields["total_days"].label = False

        # self.fields['allow_over_allocation'].label = True
        # self.fields['closed'].label = False

    class Meta:
        model = FrameworkAgreement
        fields = [
            "name",
            "start_date",
            "end_date",
            "total_days",
            "allow_over_allocation",
            "closed",
        ]


class OrganisationalUnitMemberForm(forms.ModelForm):
    member = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        widget=autocomplete.ModelSelect2(
            url="user-autocomplete",
            attrs={
                "data-minimum-input-length": 3,
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        org_unit = kwargs.pop("org_unit", None)
        super(OrganisationalUnitMemberForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field("member", style="width: 100%;"),
        )
        # self.fields['name'].label = False
        # self.fields['description'].label = False
        # self.fields['special_requirements'].label = False
        self.fields["member"].label = False

    class Meta:
        model = OrganisationalUnitMember
        fields = [
            "member",
        ]


class OrganisationalUnitMemberRolesForm(forms.ModelForm):
    roles = forms.ModelMultipleChoiceField(
        queryset=OrganisationalUnitRole.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(),
    )

    def __init__(self, *args, **kwargs):
        org_unit = kwargs.pop("org_unit", None)
        super(OrganisationalUnitMemberRolesForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field("roles", style="width: 100%;"),
        )

    class Meta:
        model = OrganisationalUnitMember
        fields = [
            "roles",
        ]


class OrganisationalUnitForm(forms.ModelForm):
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "tinymce",
                "data-tinymce": '{"height":"15rem","placeholder":"Write a description here..."}',
                "rows": 5,
            },
        ),
    )
    special_requirements = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "tinymce",
                "data-tinymce": '{"height":"15rem","placeholder":"Write an special requirements of this team here..."}',
                "rows": 5,
            },
        ),
    )
    lead = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        widget=autocomplete.ModelSelect2(
            url="user-autocomplete",
            attrs={
                "data-minimum-input-length": 3,
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        super(OrganisationalUnitForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields["name"].label = False
        self.fields["description"].label = False
        self.fields["special_requirements"].label = False
        self.fields["lead"].label = False

    class Meta:
        model = OrganisationalUnit
        fields = [
            "name",
            "description",
            "lead",
            "image",
            "special_requirements",
            "approval_required",
            "targetProfit",
            "businessHours_startTime",
            "businessHours_endTime",
            "businessHours_days",
        ]
        widgets = {
            "businessHours_days": forms.TextInput(),
            "businessHours_startTime": TimePickerInput(),
            "businessHours_endTime": TimePickerInput(),
        }


class QualificationForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(QualificationForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields["name"].label = False
        self.fields["short_name"].label = False
        self.fields["url"].label = False
        self.fields["guidance_url"].label = False
        self.fields["validity_period"].label = False
        self.fields["tags"].label = False

    class Meta:
        model = Qualification
        fields = [
            "name",
            "short_name",
            "tags",
            "validity_period",
            "url",
            "guidance_url",
        ]


class OwnQualificationRecordForm(forms.ModelForm):

    qualification = forms.ModelChoiceField(
        required=True,
        queryset=Qualification.objects.all(),
        widget=autocomplete.ModelSelect2(
            attrs={
                "data-minimum-input-length": 3,
            },
        ),
    )

    attempt_date = forms.DateField(
        required=False,
        widget=DatePickerInput(),
    )
    awarded_date = forms.DateField(
        required=False,
        widget=DatePickerInput(),
    )
    lapse_date = forms.DateField(
        required=False,
        widget=DatePickerInput(),
    )

    def __init__(self, *args, **kwargs):
        super(OwnQualificationRecordForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Div(
                Row(
                    Column(Field("qualification", style="width: 100%;")),
                ),
                Row(
                    Column(
                        Div(
                            FloatingField("status"),
                            css_class="input-group input-group-dynamic",
                        )
                    ),
                ),
                Row(
                    Column(
                        Div(
                            Field("attempt_date"),
                            css_class="input-group input-group-dynamic",
                        )
                    ),
                    Column(
                        Div(
                            Field("awarded_date"),
                            css_class="input-group input-group-dynamic",
                        )
                    ),
                    Column(
                        Div(
                            Field("lapse_date"),
                            css_class="input-group input-group-dynamic",
                        )
                    ),
                ),
                css_class="card-body p-3",
            ),
            Div(
                Div(
                    StrictButton(
                        "Save",
                        type="submit",
                        css_class="btn btn-outline-success ms-auto mb-0",
                    ),
                    css_class="button-row d-flex",
                ),
                css_class="card-footer pt-0 p-3",
            ),
        )

    class Meta:
        model = QualificationRecord
        fields = [
            "qualification",
            "status",
            "attempt_date",
            "awarded_date",
            "lapse_date",
        ]


class AwardingBodyForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(AwardingBodyForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields["name"].label = False

    class Meta:
        model = AwardingBody
        fields = ["name"]


class BillingCodeForm(forms.ModelForm):
    client = forms.ModelChoiceField(
        required=False,
        queryset=Client.objects.filter(),  # TODO: Update to only filter clients we have permission for...
        widget=autocomplete.ModelSelect2(
            attrs={
                "data-minimum-input-length": 3,
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        super(BillingCodeForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields["code"].label = False
        self.fields["client"].label = False

        # self.fields['is_chargeable'].label = False
        # self.fields['is_recoverable'].label = False
        # self.fields['is_closed'].label = False
        self.fields["region"].label = False

    class Meta:
        model = BillingCode
        fields = [
            "code",
            "client",
            "is_chargeable",
            "is_recoverable",
            "is_internal",
            "is_closed",
            "region",
        ]


class ProjectForm(forms.ModelForm):
    primary_poc = forms.ModelChoiceField(
        required=False,
        queryset=User.objects.filter(is_active=True),
        widget=autocomplete.ModelSelect2(
            url="user-autocomplete",
            attrs={
                "data-minimum-input-length": 3,
            },
        ),
    )
    unit = forms.ModelChoiceField(
        required=False,
        queryset=OrganisationalUnit.objects.filter(),
        widget=autocomplete.ModelSelect2(
        ),
    )

    overview = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "tinymce",
                "data-tinymce": '{"height":"15rem","placeholder":"Write a description here..."}',
                "rows": 5,
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        super(ProjectForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields["title"].label = False
        self.fields["overview"].label = False

        self.fields["primary_poc"].label = False
        self.fields["status"].label = False
        self.fields["unit"].label = False

    class Meta:
        model = Project
        fields = [
            "title",
            "overview",
            "primary_poc",
            "status",
            "unit",
        ]

class ServiceForm(forms.ModelForm):
    owners = forms.ModelMultipleChoiceField(
        required=False,
        queryset=User.objects.filter(is_active=True),
        widget=autocomplete.ModelSelect2Multiple(
            url="user-autocomplete",
            attrs={
                "data-minimum-input-length": 3,
            },
        ),
    )

    skillsRequired = forms.ModelMultipleChoiceField(
        required=False,
        queryset=Skill.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(),
    )

    skillsDesired = forms.ModelMultipleChoiceField(
        required=False,
        queryset=Skill.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(),
    )

    def __init__(self, *args, **kwargs):
        super(ServiceForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields["name"].label = False
        self.fields["description"].label = False

        self.fields["owners"].label = False
        self.fields["link"].label = False
        self.fields["skillsRequired"].label = False
        self.fields["skillsDesired"].label = False

    class Meta:
        model = Service
        fields = [
            "name",
            "owners",
            "description",
            "link",
            "skillsRequired",
            "skillsDesired",
        ]


class WFTaskForm(forms.ModelForm):
    status = forms.IntegerField(
        widget=forms.Select(),
    )

    def __init__(self, *args, **kwargs):
        status_choices = kwargs.pop("status_choices")
        if "applied_model" in kwargs:
            _ = kwargs.pop("applied_model")
        super(WFTaskForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)

        self.fields["status"].widget.choices = status_choices
        self.fields["status"].label = False
        self.fields["task"].label = False

    class Meta:
        model = WorkflowTask
        fields = ["status", "task"]


class SkillForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(SkillForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields["name"].label = False
        self.fields["description"].label = False

    class Meta:
        model = Skill
        fields = ["name", "description"]


class SkillCatForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(SkillCatForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields["name"].label = False
        self.fields["description"].label = False

    class Meta:
        model = SkillCategory
        fields = ["name", "description"]


class JobSupportTeamRoleForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(JobSupportTeamRoleForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Div(
                Row(Div(Field("user"), css_class="input-group input-group-dynamic")),
                Row(Div(Field("role"), css_class="input-group input-group-dynamic")),
                Row(
                    Column(
                        Div(
                            Field("allocated_hours"),
                            css_class="input-group input-group-dynamic",
                        )
                    ),
                    Column(
                        Div(
                            Field("billed_hours"),
                            css_class="input-group input-group-dynamic",
                        )
                    ),
                ),
                css_class="modal-body pt-3",
            ),
            Div(
                Div(
                    StrictButton(
                        "Save",
                        type="submit",
                        css_class="btn btn-outline-success ms-auto mb-0",
                    ),
                    css_class="button-row d-flex",
                ),
                css_class="modal-footer",
            ),
        )

    class Meta:
        model = JobSupportTeamRole
        fields = ("user", "role", "allocated_hours", "billed_hours")
