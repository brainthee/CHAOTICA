from django.urls import include, path
from . import views
from .feeds import ScheduleFeed, ScheduleFamilyFeed
from rest_framework import routers

router = routers.DefaultRouter()
router.register(r"users", views.UserViewSet, basename="user")
router.register(r"jobs", views.JobViewSet, basename="job")
router.register(
    r"orgunit", views.OrganisationalUnitViewSet, basename="organisationalunit"
)
router.register(r"client", views.ClientViewSet, basename="client")

urlpatterns = [
    # Extra profile bits
    path("api/", include(router.urls)),
    path("api-auth/", include("rest_framework.urls", namespace="rest_framework")),
    path(
        "profile/qualifications/",
        views.OwnQualificationRecordListView.as_view(),
        name="view_own_qualifications",
    ),
    path(
        "profile/qualifications/add",
        views.add_own_qualification,
        name="add_own_qualification",
    ),
    path(
        "profile/qualifications/<int:pk>/update",
        views.update_own_qualification,
        name="update_own_qualification",
    ),
    # Misc
    path("stats/", views.view_stats, name="view_stats"),
    path("reports/", views.view_reports, name="view_reports"),
    path("tasks/", views.run_tasks, name="run_tasks"),
    # Scheduler
    path("schedule/feed/reset", views.reset_cal_feed, name="reset_cal_feed"),
    path(
        "schedule/feed/family/reset",
        views.reset_cal_family_feed,
        name="reset_cal_family_feed",
    ),
    path(
        "schedule/feed/family/<str:cal_key>",
        ScheduleFamilyFeed(),
        name="view_own_schedule_feed_family",
    ),
    path("schedule/feed/<str:cal_key>", ScheduleFeed(), name="view_own_schedule_feed"),
    path(
        "schedule/timeslots",
        views.view_own_schedule_timeslots,
        name="view_own_schedule_timeslots",
    ),
    path(
        "schedule/holidays", views.view_own_schedule_holidays, name="view_own_schedule_holidays"
    ),
    path("scheduler/", views.view_scheduler, name="view_scheduler"),
    path(
        "scheduler/members", views.view_scheduler_members, name="view_scheduler_members"
    ),
    path(
        "scheduler/timeslots", views.view_scheduler_slots, name="view_scheduler_slots"
    ),
    # Create paths
    path(
        "scheduler/timeslots/phase/create",
        views.create_scheduler_phase_slot,
        name="create_scheduler_phase_slot",
    ),
    path(
        "scheduler/timeslots/project/create",
        views.create_scheduler_project_slot,
        name="create_scheduler_project_slot",
    ),
    path(
        "scheduler/timeslots/internal/create",
        views.create_scheduler_internal_slot,
        name="create_scheduler_internal_slot",
    ),
    # change paths
    path(
        "scheduler/timeslot/change/",
        views.change_scheduler_slot,
        name="change_scheduler_slot",
    ),
    path(
        "scheduler/timeslot/change/<int:pk>",
        views.change_scheduler_slot,
        name="change_scheduler_slot",
    ),
    path(
        "scheduler/timeslot/change_date/",
        views.change_scheduler_slot_date,
        name="change_scheduler_slot_date",
    ),
    path(
        "scheduler/timeslot/change_date/<int:pk>",
        views.change_scheduler_slot_date,
        name="change_scheduler_slot_date",
    ),
    path(
        "scheduler/timeslot/delete/<int:pk>",
        views.JobSlotDeleteView.as_view(),
        name="delete_scheduler_slot",
    ),
    # Comment paths
    path(
        "scheduler/timeslots/comment/create",
        views.create_scheduler_comment,
        name="create_scheduler_comment",
    ),
    path(
        "scheduler/timeslots/comment/change/",
        views.change_scheduler_slot_comment,
        name="change_scheduler_slot_comment",
    ),
    path(
        "scheduler/timeslots/comment/change/<int:pk>",
        views.change_scheduler_slot_comment,
        name="change_scheduler_slot_comment",
    ),
    path(
        "scheduler/timeslots/comment/change_date/",
        views.change_scheduler_slot_comment_date,
        name="change_scheduler_slot_comment_date",
    ),
    path(
        "scheduler/timeslots/comment/change_date/<int:pk>",
        views.change_scheduler_slot_comment_date,
        name="change_scheduler_slot_comment_date",
    ),
    path(
        "scheduler/timeslots/comment/delete/<int:pk>",
        views.SlotCommentDeleteView.as_view(),
        name="delete_scheduler_slot_comment",
    ),
    
    path(
        "scheduler/timeslots/clear_range",
        views.clear_scheduler_range,
        name="clear_scheduler_range",
    ),
    # Project CRUD
    path("projects/", views.ProjectListView.as_view(), name="project_list"),
    path("project/create/", views.ProjectCreateView.as_view(), name="project_create"),
    path(
        "project/<str:slug>/",
        views.ProjectDetailView.as_view(),
        name="project_detail",
    ),
    path(
        "project/<str:slug>/update/",
        views.ProjectUpdateView.as_view(),
        name="project_update",
    ),
    path(
        "project/<str:slug>/schedule/slot/<int:pk>/delete",
        views.ProjectSlotDeleteView.as_view(),
        name="project_slot_delete",
    ),
    path(
        "project/<str:slug>/delete/",
        views.ProjectDeleteView.as_view(),
        name="project_delete",
    ),
    # Job CRUD
    path("jobs/", views.JobListView.as_view(), name="job_list"),
    path(
        "jobs/autocomplete/billingcodes",
        views.JobBillingCodeAutocomplete.as_view(),
        name="job_autocomplete_billingcodes",
    ),
    path("job/create/", views.JobCreateView.as_view(), name="job_create"),
    path("job/<str:slug>/", views.JobDetailView.as_view(), name="job_detail"),
    path(
        "job/<str:slug>/update/workflow/<int:new_state>",
        views.job_update_workflow,
        name="job_update_workflow",
    ),
    path("job/<str:slug>/update/note", views.job_create_note, name="job_create_note"),
    path("job/<str:slug>/edit/scope", views.job_edit_scope, name="job_edit_scope"),
    path(
        "job/<str:slug>/update/scope",
        views.JobUpdateScopeView.as_view(),
        name="job_update_scope",
    ),
    path("job/<str:slug>/update/", views.JobUpdateView.as_view(), name="job_update"),
    path("job/<str:slug>/delete/", views.JobDeleteView.as_view(), name="job_delete"),
    path(
        "job/<str:slug>/support/add",
        views.job_support_team_add,
        name="job_support_team_add",
    ),
    path(
        "job/<str:slug>/support/<int:pk>/edit",
        views.job_support_team_edit,
        name="job_support_team_edit",
    ),
    path(
        "job/<str:slug>/support/<int:pk>/mark_used",
        views.job_support_team_mark_used,
        name="job_support_team_mark_used",
    ),
    path(
        "job/<str:slug>/support/<int:pk>/delete",
        views.job_support_team_delete,
        name="job_support_team_delete",
    ),
    path(
        "job/<str:slug>/schedule/", views.JobScheduleView.as_view(), name="job_schedule"
    ),
    path(
        "job/<str:slug>/schedule/gantt",
        views.view_job_schedule_gantt_data,
        name="view_job_schedule_gantt_data",
    ),
    path(
        "job/<str:slug>/schedule/members",
        views.view_job_schedule_members,
        name="view_job_schedule_members",
    ),
    path(
        "job/<str:slug>/schedule/slots",
        views.view_job_schedule_slots,
        name="view_job_schedule_slots",
    ),
    path(
        "job/<str:slug>/schedule/slot",
        views.change_job_schedule_slot,
        name="change_job_schedule_slot",
    ),
    path(
        "job/<str:slug>/schedule/slot/<int:pk>",
        views.change_job_schedule_slot,
        name="change_job_schedule_slot",
    ),
    path(
        "job/<str:slug>/schedule/slot/<int:pk>/delete",
        views.JobSlotDeleteView.as_view(),
        name="job_slot_delete",
    ),
    path(
        "job/<str:slug>/assign/framework",
        views.assign_job_framework,
        name="assign_job_framework",
    ),
    path(
        "job/<str:slug>/assign/billingcodes",
        views.assign_job_billingcodes,
        name="assign_job_billingcodes",
    ),
    path(
        "job/<str:slug>/assign/primay_poc", views.assign_job_poc, name="assign_job_poc"
    ),
    path(
        "job/<str:slug>/assign/<str:field>",
        views.assign_job_field,
        name="assign_job_field",
    ),
    # Phase CRUD
    path(
        "autocomplete/phases",
        views.PhaseAutocomplete.as_view(),
        name="phase-autocomplete",
    ),
    path(
        "job/<str:job_slug>/phase/create/",
        views.PhaseCreateView.as_view(),
        name="phase_create",
    ),
    path(
        "job/<str:job_slug>/phase/<str:slug>/",
        views.PhaseDetailView.as_view(),
        name="phase_detail",
    ),
    path(
        "job/<str:job_slug>/phase/<str:slug>/fire_notifications",
        views.phase_refire_notifications,
        name="phase_refire_notifications",
    ),
    path(
        "job/<str:job_slug>/phase/<str:slug>/update/note",
        views.phase_create_note,
        name="phase_create_note",
    ),
    path(
        "job/<str:job_slug>/phase/<str:slug>/update/workflow/<int:new_state>",
        views.phase_update_workflow,
        name="phase_update_workflow",
    ),
    path(
        "job/<str:job_slug>/phase/<str:slug>/update/",
        views.PhaseUpdateView.as_view(),
        name="phase_update",
    ),
    path(
        "job/<str:job_slug>/phase/<str:slug>/edit/delivery",
        views.phase_edit_delivery,
        name="phase_edit_delivery",
    ),
    # path('job/<str:job_slug>/phase/<str:slug>/edit/qa', views.phase_edit_qa, name='phase_edit_qa'),
    path(
        "job/<str:job_slug>/phase/<str:slug>/feedback/techqa",
        views.phase_feedback_techqa,
        name="phase_feedback_techqa",
    ),
    path(
        "job/<str:job_slug>/phase/<str:slug>/feedback/presqa",
        views.phase_feedback_presqa,
        name="phase_feedback_presqa",
    ),
    path(
        "job/<str:job_slug>/phase/<str:slug>/feedback/scope",
        views.phase_feedback_scope,
        name="phase_feedback_scope",
    ),
    path(
        "job/<str:job_slug>/phase/<str:slug>/rating/techqa",
        views.phase_rating_techqa,
        name="phase_rating_techqa",
    ),
    path(
        "job/<str:job_slug>/phase/<str:slug>/rating/presqa",
        views.phase_rating_presqa,
        name="phase_rating_presqa",
    ),
    path(
        "job/<str:job_slug>/phase/<str:slug>/rating/scope",
        views.phase_rating_scope,
        name="phase_rating_scope",
    ),
    path(
        "job/<str:job_slug>/phase/<str:slug>/delete/",
        views.PhaseDeleteView.as_view(),
        name="phase_delete",
    ),
    path(
        "job/<str:job_slug>/phase/<str:slug>/schedule/",
        views.PhaseScheduleView.as_view(),
        name="phase_schedule",
    ),
    path(
        "job/<str:job_slug>/phase/<str:slug>/schedule/gantt",
        views.view_phase_schedule_gantt_data,
        name="view_phase_schedule_gantt_data",
    ),
    path(
        "job/<str:job_slug>/phase/<str:slug>/schedule/slots",
        views.view_phase_schedule_slots,
        name="view_phase_schedule_slots",
    ),
    path(
        "job/<str:job_slug>/phase/<str:slug>/schedule/members",
        views.view_phase_schedule_members,
        name="view_phase_schedule_members",
    ),
    path(
        "job/<str:job_slug>/phase/<str:slug>/assign/<str:field>",
        views.assign_phase_field,
        name="assign_phase_field",
    ),
    # Client CRUD
    path("clients/", views.ClientListView.as_view(), name="client_list"),
    path("client/create/", views.ClientCreateView.as_view(), name="client_create"),
    path("client/<str:slug>/", views.ClientDetailView.as_view(), name="client_detail"),
    path(
        "client/<str:slug>/update/",
        views.ClientUpdateView.as_view(),
        name="client_update",
    ),
    path(
        "client/<str:slug>/delete/",
        views.ClientDeleteView.as_view(),
        name="client_delete",
    ),
    path(
        "client/<str:slug>/merge",
        views.client_merge,
        name="client_merge",
    ),
    # Client Contact CRUD
    path(
        "client/<str:client_slug>/contact/create/",
        views.ClientContactCreateView.as_view(),
        name="client_contact_create",
    ),
    path(
        "client/<str:client_slug>/contact/<int:pk>/",
        views.ClientContactDetailView.as_view(),
        name="client_contact_detail",
    ),
    path(
        "client/<str:client_slug>/contact/<int:pk>/update/",
        views.ClientContactUpdateView.as_view(),
        name="client_contact_update",
    ),
    path(
        "client/<str:client_slug>/contact/<int:pk>/delete/",
        views.ClientContactDeleteView.as_view(),
        name="client_contact_delete",
    ),
    # Client framework CRUD
    path(
        "client/<str:client_slug>/framework/create/",
        views.ClientFrameworkCreateView.as_view(),
        name="client_framework_create",
    ),
    path(
        "client/<str:client_slug>/framework/<int:pk>/",
        views.ClientFrameworkDetailView.as_view(),
        name="client_framework_detail",
    ),
    path(
        "client/<str:client_slug>/framework/<int:pk>/update/",
        views.ClientFrameworkUpdateView.as_view(),
        name="client_framework_update",
    ),
    path(
        "client/<str:client_slug>/framework/<int:pk>/delete/",
        views.ClientFrameworkDeleteView.as_view(),
        name="client_framework_delete",
    ),
    # Billing Code CRUD
    path(
        "ops/billingcodes/",
        views.BillingCodeListView.as_view(),
        name="billingcode_list",
    ),
    path(
        "ops/billingcode/create/",
        views.BillingCodeCreateView.as_view(),
        name="billingcode_create",
    ),
    path(
        "ops/billingcode/<str:code>/",
        views.BillingCodeDetailView.as_view(),
        name="billingcode_detail",
    ),
    path(
        "ops/billingcode/<str:code>/update/",
        views.BillingCodeUpdateView.as_view(),
        name="billingcode_update",
    ),
    path(
        "ops/billingcode/<str:code>/delete/",
        views.BillingCodeDeleteView.as_view(),
        name="billingcode_delete",
    ),
    # Service CRUD
    path("ops/services/", views.ServiceListView.as_view(), name="service_list"),
    path(
        "ops/service/create/", views.ServiceCreateView.as_view(), name="service_create"
    ),
    path(
        "ops/service/<str:slug>/",
        views.ServiceDetailView.as_view(),
        name="service_detail",
    ),
    path(
        "ops/service/<str:slug>/update/",
        views.ServiceUpdateView.as_view(),
        name="service_update",
    ),
    path(
        "ops/service/<str:slug>/delete/",
        views.ServiceDeleteView.as_view(),
        name="service_delete",
    ),
    # Checklists
    path("ops/workflow_tasks/", views.WFTaskListView.as_view(), name="wf_tasks_list"),
    path(
        "ops/workflow_tasks/create/<str:targetType>",
        views.WFTaskCreateView.as_view(),
        name="wf_task_create",
    ),
    path(
        "ops/workflow_tasks/<int:pk>/update/",
        views.WFTaskUpdateView.as_view(),
        name="wf_task_update",
    ),
    path(
        "ops/workflow_tasks/<int:pk>/delete/",
        views.WFTaskDeleteView.as_view(),
        name="wf_task_delete",
    ),
    # OrganisationalUnit CRUD
    path(
        "ops/units/",
        views.OrganisationalUnitListView.as_view(),
        name="organisationalunit_list",
    ),
    path(
        "ops/unit/create/",
        views.OrganisationalUnitCreateView.as_view(),
        name="organisationalunit_create",
    ),
    path(
        "ops/unit/<str:slug>/members/add",
        views.organisationalunit_add,
        name="organisationalunit_add",
    ),
    path(
        "ops/unit/<str:slug>/members/join",
        views.organisationalunit_join,
        name="organisationalunit_join",
    ),
    path(
        "ops/unit/<str:slug>/members/review/<int:member_pk>",
        views.organisationalunit_review_join_request,
        name="review_join_request",
    ),
    path(
        "ops/unit/<str:slug>/members/manage_roles/<int:member_pk>",
        views.organisationalunit_manage_roles,
        name="organisationalunit_manage_roles",
    ),
    path(
        "ops/unit/<str:slug>/detail",
        views.OrganisationalUnitDetailView.as_view(),
        name="organisationalunit_detail",
    ),
    path(
        "ops/unit/<str:slug>/update/",
        views.OrganisationalUnitUpdateView.as_view(),
        name="organisationalunit_update",
    ),
    path(
        "ops/unit/<str:slug>/delete/",
        views.OrganisationalUnitDeleteView.as_view(),
        name="organisationalunit_delete",
    ),
    # Skill CRUD
    path("ops/skills/", views.SkillListView.as_view(), name="skill_list"),
    path("ops/skill/<str:slug>/", views.SkillDetailView.as_view(), name="skill_detail"),
    path(
        "ops/skill/<str:slug>/update/",
        views.SkillUpdateView.as_view(),
        name="skill_update",
    ),
    path(
        "ops/skill/<str:slug>/delete/",
        views.SkillDeleteView.as_view(),
        name="skill_delete",
    ),
    path(
        "ops/skill_category/create/",
        views.SkillCatCreateView.as_view(),
        name="skill_cat_create",
    ),
    path(
        "ops/skill_category/<str:catSlug>/create/",
        views.SkillCreateView.as_view(),
        name="skill_create",
    ),
    path(
        "ops/skill_category/<str:slug>/update/",
        views.SkillCatUpdateView.as_view(),
        name="skill_cat_update",
    ),
    path(
        "ops/skill_category/<str:slug>/delete/",
        views.SkillCatDeleteView.as_view(),
        name="skill_cat_delete",
    ),
    # Qualifications CRUD
    path(
        "ops/qualifications/",
        views.QualificationListView.as_view(),
        name="qualification_list",
    ),
    path(
        "ops/qualifications/awardingbody/create/",
        views.QualificationAwardingBodyCreateView.as_view(),
        name="qualification_awardingbody_create",
    ),
    path(
        "ops/qualification/<str:bodySlug>/create",
        views.QualificationCreateView.as_view(),
        name="qualification_create",
    ),
    path(
        "ops/qualification/<str:bodySlug>/<str:slug>",
        views.QualificationDetailView.as_view(),
        name="qualification_detail",
    ),
    path(
        "ops/qualification/<str:bodySlug>/<str:slug>/update/",
        views.QualificationUpdateView.as_view(),
        name="qualification_update",
    ),
    path(
        "ops/qualification/<str:bodySlug>/<str:slug>/delete/",
        views.QualificationDeleteView.as_view(),
        name="qualification_delete",
    ),
    path(
        "autocomplete/projects",
        views.ProjectAutocomplete.as_view(),
        name="project-autocomplete",
    ),
    path("autocomplete/jobs", views.JobAutocomplete.as_view(), name="job-autocomplete"),
]
