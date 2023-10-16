from django.urls import path
from . import views
from .feeds import ScheduleFeed, ScheduleFamilyFeed

urlpatterns = [
    path('schedule/feed/reset', views.reset_cal_feed, name='reset_cal_feed'),
    path('schedule/feed/family/reset', views.reset_cal_family_feed, name='reset_cal_family_feed'),
    path('schedule/feed/family/<str:cal_key>', ScheduleFamilyFeed(), name='view_own_schedule_feed_family'),
    path('schedule/feed/<str:cal_key>', ScheduleFeed(), name='view_own_schedule_feed'),
    path('schedule/timeslots', views.view_own_schedule_timeslots, name='view_own_schedule_timeslots'),
    path('scheduler/', views.view_scheduler, name='view_scheduler'),
    path('scheduler/members', views.view_scheduler_members, name='view_scheduler_members'),
    path('scheduler/events', views.view_scheduler_slots, name='view_scheduler_slots'),
    path('stats/', views.view_stats, name='view_stats'),
    path('reports/', views.view_reports, name='view_reports'),
    path('tasks/', views.run_tasks, name='run_tasks'),

    # Job CRUD
    path('jobs/', views.JobListView.as_view(), name='job_list'),
    path('job/create/', views.JobCreateView.as_view(), name='job_create'),
    path('job/<str:slug>/', views.JobDetailView.as_view(), name='job_detail'),
    path('job/<str:slug>/update/workflow/<int:new_state>', views.job_update_workflow, name='job_update_workflow'),
    path('job/<str:slug>/update/note', views.job_create_note, name='job_create_note'),
    path('job/<str:slug>/edit/scope', views.job_edit_scope, name='job_edit_scope'),
    path('job/<str:slug>/update/scope', views.JobUpdateScopeView.as_view(), name='job_update_scope'),
    path('job/<str:slug>/update/', views.JobUpdateView.as_view(), name='job_update'),
    path('job/<str:slug>/delete/', views.JobDeleteView.as_view(), name='job_delete'),
    path('job/<str:slug>/schedule/', views.JobScheduleView.as_view(), name='job_schedule'),   
    path('job/<str:slug>/schedule/members', views.view_job_schedule_members, name='view_job_schedule_members'), 
    path('job/<str:slug>/schedule/slots', views.view_job_schedule_slots, name='view_job_schedule_slots'),

    path('job/<str:slug>/schedule/slot', views.change_job_schedule_slot, name='change_job_schedule_slot'),
    path('job/<str:slug>/schedule/slot/<int:pk>', views.change_job_schedule_slot, name='change_job_schedule_slot'),
    path('job/<str:slug>/schedule/slot/<int:pk>/delete', views.SlotDeleteView.as_view(), name='job_slot_delete'),

    path('job/<str:slug>/assign/primay_poc', views.assign_job_poc, name='assign_job_poc'),
    path('job/<str:slug>/assign/<str:field>', views.assign_job_field, name='assign_job_field'),

    # Phase CRUD
    path('job/<str:jobSlug>/phase/create/', views.PhaseCreateView.as_view(), name='phase_create'),
    path('job/<str:jobSlug>/phase/<str:slug>/', views.PhaseDetailView.as_view(), name='phase_detail'),
    path('job/<str:jobSlug>/phase/<str:slug>/update/note', views.PhaseCreateNote, name='phase_create_note'),
    path('job/<str:jobSlug>/phase/<str:slug>/update/workflow/<int:new_state>', views.PhaseUpdateWorkflow, name='phase_update_workflow'),
    path('job/<str:jobSlug>/phase/<str:slug>/update/', views.PhaseUpdateView.as_view(), name='phase_update'),

    path('job/<str:jobSlug>/phase/<str:slug>/edit/delivery', views.phase_edit_delivery, name='phase_edit_delivery'),
    # path('job/<str:jobSlug>/phase/<str:slug>/edit/qa', views.phase_edit_qa, name='phase_edit_qa'),
    path('job/<str:jobSlug>/phase/<str:slug>/feedback/techqa', views.phase_feedback_techqa, name='phase_feedback_techqa'),
    path('job/<str:jobSlug>/phase/<str:slug>/feedback/presqa', views.phase_feedback_presqa, name='phase_feedback_presqa'),
    path('job/<str:jobSlug>/phase/<str:slug>/feedback/scope', views.phase_feedback_scope, name='phase_feedback_scope'),
    path('job/<str:jobSlug>/phase/<str:slug>/rating/techqa', views.phase_rating_techqa, name='phase_rating_techqa'),
    path('job/<str:jobSlug>/phase/<str:slug>/rating/presqa', views.phase_rating_presqa, name='phase_rating_presqa'),
    path('job/<str:jobSlug>/phase/<str:slug>/rating/scope', views.phase_rating_scope, name='phase_rating_scope'),
    path('job/<str:jobSlug>/phase/<str:slug>/delete/', views.PhaseDeleteView.as_view(), name='phase_delete'),

    path('job/<str:jobSlug>/phase/<str:slug>/schedule/', views.PhaseScheduleView.as_view(), name='phase_schedule'),  
    path('job/<str:jobSlug>/phase/<str:slug>/schedule/slots', views.view_phase_schedule_slots, name='view_phase_schedule_slots'),
    path('job/<str:jobSlug>/phase/<str:slug>/schedule/members', views.view_phase_schedule_members, name='view_phase_schedule_members'),

    path('job/<str:jobSlug>/phase/<str:slug>/assign/<str:field>', views.assign_phase_field, name='assign_phase_field'),

    # Client CRUD
    path('clients/', views.ClientListView.as_view(), name='client_list'),
    path('client/create/', views.ClientCreateView.as_view(), name='client_create'),
    path('client/<str:slug>/', views.ClientDetailView.as_view(), name='client_detail'),
    path('client/<str:slug>/update/', views.ClientUpdateView.as_view(), name='client_update'),
    path('client/<str:slug>/delete/', views.ClientDeleteView.as_view(), name='client_delete'),

    # Client CRUD
    path('client/<str:slug>/contact/create/', views.ClientContactCreateView.as_view(), name='client_contact_create'),
    path('client/<str:slug>/contact/<int:pk>/', views.ClientContactDetailView.as_view(), name='client_contact_detail'),
    path('client/<str:slug>/contact/<int:pk>/update/', views.ClientContactUpdateView.as_view(), name='client_contact_update'),
    path('client/<str:slug>/contact/<int:pk>/delete/', views.ClientContactDeleteView.as_view(), name='client_contact_delete'),

    # Service CRUD
    path('ops/services/', views.ServiceListView.as_view(), name='service_list'),
    path('ops/service/create/', views.ServiceCreateView.as_view(), name='service_create'),
    path('ops/service/<str:slug>/', views.ServiceDetailView.as_view(), name='service_detail'),
    path('ops/service/<str:slug>/update/', views.ServiceUpdateView.as_view(), name='service_update'),
    path('ops/service/<str:slug>/delete/', views.ServiceDeleteView.as_view(), name='service_delete'),

    # Checklists
    path('ops/workflow_tasks/', views.WFTaskListView.as_view(), name='wf_tasks_list'),
    path('ops/workflow_tasks/create/<str:targetType>', views.WFTaskCreateView.as_view(), name='wf_task_create'),
    path('ops/workflow_tasks/<int:pk>/update/', views.WFTaskUpdateView.as_view(), name='wf_task_update'),
    path('ops/workflow_tasks/<int:pk>/delete/', views.WFTaskDeleteView.as_view(), name='wf_task_delete'),

    # OrganisationalUnit CRUD
    path('ops/units/', views.OrganisationalUnitListView.as_view(), name='organisationalunit_list'),
    path('ops/unit/create/', views.OrganisationalUnitCreateView.as_view(), name='organisationalunit_create'),
    path('ops/unit/<str:slug>/join', views.OrganisationalUnit_join, name='organisationalunit_join'),
    path('ops/unit/<str:slug>/review_join_request/<int:memberPK>', views.OrganisationalUnit_review_join_request, name='review_join_request'),
    path('ops/unit/<str:slug>/detail', views.OrganisationalUnitDetailView.as_view(), name='organisationalunit_detail'),
    path('ops/unit/<str:slug>/update/', views.OrganisationalUnitUpdateView.as_view(), name='organisationalunit_update'),
    path('ops/unit/<str:slug>/delete/', views.OrganisationalUnitDeleteView.as_view(), name='organisationalunit_delete'),

    # Skill CRUD
    path('ops/skills/', views.SkillListView.as_view(), name='skill_list'),
    path('ops/skill/<str:slug>/', views.SkillDetailView.as_view(), name='skill_detail'),
    path('ops/skill/<str:slug>/update/', views.SkillUpdateView.as_view(), name='skill_update'),
    path('ops/skill/<str:slug>/delete/', views.SkillDeleteView.as_view(), name='skill_delete'),
    
    path('ops/skill_category/create/', views.SkillCatCreateView.as_view(), name='skill_cat_create'),
    path('ops/skill_category/<str:catSlug>/create/', views.SkillCreateView.as_view(), name='skill_create'),
    path('ops/skill_category/<str:slug>/update/', views.SkillCatUpdateView.as_view(), name='skill_cat_update'),
    path('ops/skill_category/<str:slug>/delete/', views.SkillCatDeleteView.as_view(), name='skill_cat_delete'),
]