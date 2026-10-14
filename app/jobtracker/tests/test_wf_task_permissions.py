"""Workflow checklists are global config: every view needs the matching
model permission, not just a login."""

from django.test import TestCase, override_settings
from django.urls import reverse
from guardian.shortcuts import assign_perm

from chaotica_utils.models import User
from jobtracker.models import WorkflowTask


@override_settings(ALLOWED_HOSTS=["*", "testserver"])
class WorkflowTaskPermissionTests(TestCase):
    def setUp(self):
        User.objects.create_user(email="bootstrap@test.com", password="pw12345")
        self.user = User.objects.create_user(email="u@test.com", password="pw12345")
        self.admin = User.objects.create_user(email="a@test.com", password="pw12345")
        for perm in ("view", "add", "change", "delete"):
            assign_perm(f"jobtracker.{perm}_workflowtask", self.admin)
        self.task = WorkflowTask.objects.create(
            appliedModel=WorkflowTask.WF_JOB, status=0, task="Check scope"
        )

    def _urls(self):
        return [
            reverse("wf_tasks_list"),
            reverse("wf_task_create", args=["job"]),
            reverse("wf_task_update", args=[self.task.pk]),
            reverse("wf_task_delete", args=[self.task.pk]),
        ]

    def test_plain_user_gets_403_everywhere(self):
        self.client.force_login(self.user)
        for url in self._urls():
            resp = self.client.get(url, HTTP_HOST="testserver")
            self.assertEqual(resp.status_code, 403, url)
        resp = self.client.post(
            reverse("wf_task_delete", args=[self.task.pk]), HTTP_HOST="testserver"
        )
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(WorkflowTask.objects.filter(pk=self.task.pk).exists())

    def test_permitted_user_can_view(self):
        self.client.force_login(self.admin)
        for url in self._urls():
            resp = self.client.get(url, HTTP_HOST="testserver")
            self.assertEqual(resp.status_code, 200, url)
