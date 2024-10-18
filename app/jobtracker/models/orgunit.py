from django.db import models
from django.conf import settings
from chaotica_utils.utils import unique_slug_generator
from django.urls import reverse
from simple_history.models import HistoricalRecords
from guardian.shortcuts import (
    assign_perm,
    remove_perm,
    get_user_perms,
    get_users_with_perms,
)
from django.db.models import JSONField
import uuid, os, random
from chaotica_utils.models import User, get_sentinel_user
from chaotica_utils.enums import UnitRoles
from decimal import Decimal
from django.templatetags.static import static
from django_bleach.models import BleachField
from django.db.models.functions import Lower
from django.contrib.auth.models import Permission


def _default_business_days():
    return [1, 2, 3, 4, 5]


def get_media_image_file_path(instance, filename):
    ext = filename.split(".")[-1]
    filename = "%s.%s" % (uuid.uuid4(), ext)
    return os.path.join("media/images", filename)


class OrganisationalUnit(models.Model):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(null=False, default="", unique=True)
    description = BleachField(default="", null=True)
    image = models.ImageField(
        default="default.jpg", upload_to=get_media_image_file_path
    )
    targetProfit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(37),
        verbose_name="Target Profit",
        help_text="The % target profit for this unit",
    )
    businessHours_startTime = models.TimeField("Start Time", default="09:00:00")
    businessHours_endTime = models.TimeField("End Time", default="17:30:00")
    businessHours_days = JSONField(
        verbose_name="Days",
        null=True,
        blank=True,
        default=_default_business_days,
        help_text="An int array with the numbers equaling the day of the week. Sunday == 0, Monday == 2 etc",
    )
    approval_required = models.BooleanField(
        "Approval Required",
        default=True,
        help_text="Approval by a Manager is required to join the unit",
    )
    special_requirements = BleachField(blank=True, null=True)
    history = HistoricalRecords()
    lead = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="units_lead",
        null=True,
        on_delete=models.DO_NOTHING,
    )

    class Meta:
        ordering = [Lower("name")]
        permissions = (
            ("manage_members", "Assign Members"),
            # Job permissions
            ("can_view_jobs", "Can view jobs"),
            ("can_add_job", "Can add jobs"),
            ("can_update_job", "Can update jobs"),
            ("can_refire_notifications_job", "Can refire notifications for jobs"),
            ("can_delete_job", "Can delete jobs"),
            ("can_add_note_job", "Can add a note to jobs"),
            ("can_assign_poc_job", "Can assign a Point of Contact to jobs"),
            ("can_manage_framework_job", "Can assign a Point of Contact to jobs"),
            ("can_add_phases", "Can add phases"),
            ("can_delete_phases", "Can add phases"),
            ("can_schedule_job", "Can schedule phases"),
            ("view_users_schedule", "View Members Schedule"),
            ("view_job_schedule", "View a Job's Schedule"),
            ("can_scope_jobs", "Can scope jobs"),
            ("can_signoff_scopes", "Can signoff scopes"),
            ("can_signoff_own_scopes", "Can signoff own scopes"),
            ("can_tqa_jobs", "Can TQA jobs"),
            ("can_pqa_jobs", "Can PQA jobs"),
            # Notification pools
            ("notification_pool_scoping", "Scoping Pool"),
            ("notification_pool_scheduling", "Scheduling Pool"),
            ("notification_pool_tqa", "TQA Pool"),
            ("notification_pool_pqa", "PQA Pool"),
            # Leave
            (
                "can_view_all_leave_requests",
                "Can view all leave for members of the unit",
            ),
            ("can_approve_leave_requests", "Can approve leave requests"),
        )

    def sync_permissions(self):
        for user in self.get_allMembers():
            # Ensure the permissions are set right!
            existing_perms = list(
                get_user_perms(user, self).values_list("codename", flat=True)
            )

            expected_perms = []
            # get a combined list of perms from their roles...
            for ms in OrganisationalUnitMember.objects.filter(
                unit=self, member=user, left_date__isnull=True
            ):
                perm_objs = Permission.objects.filter(
                    pk__in=ms.roles.all().values_list("permissions").distinct()
                )
                for role_perm in perm_objs:
                    if role_perm.codename not in expected_perms:
                        expected_perms.append(role_perm.codename)

            if expected_perms:
                # First lets add missing perms...
                for new_perm in expected_perms:
                    if new_perm not in existing_perms:
                        assign_perm(new_perm, user, self)

                # Now lets remove old perms
                for old_perm in existing_perms:
                    if old_perm not in expected_perms:
                        remove_perm(old_perm, user, self)
            else:
                if existing_perms:
                    # We should not have any permissions! Clear them all
                    for perm in existing_perms:
                        remove_perm(perm, user, self)

    def __str__(self):
        return self.name

    def get_managers(self):
        ids = []
        for mgr in OrganisationalUnitMember.objects.filter(
            unit=self, role=UnitRoles.MANAGER
        ):
            if mgr.member.pk not in ids:
                ids.append(mgr.member.pk)
        if ids:
            return User.objects.filter(pk__in=ids)
        else:
            return User.objects.none()

    def get_activeMembers(self):
        ids = []
        for mgr in OrganisationalUnitMember.objects.filter(
            unit=self, left_date__isnull=True, member__is_active=True,
        ):
            if mgr.member.pk not in ids:
                ids.append(mgr.member.pk)
        if ids:
            return User.objects.filter(pk__in=ids)
        else:
            return User.objects.none()

    def get_activeMemberships(self):
        return self.members.filter(
            left_date__isnull=True, member__is_active=True,
        )

    def get_active_members_with_perm(self, permission_str, include_su=False):
        members = self.get_activeMembers()
        return (
            get_users_with_perms(
                self, with_superusers=include_su, only_with_perms_in=[permission_str]
            )
            .filter(pk__in=members)
            .distinct()
        )

    def get_allMembers(self):
        ids = []
        return User.objects.filter(pk__in=
                                   self.members.all().values_list("member__pk", flat=True))
        # for mgr in OrganisationalUnitMember.objects.filter(unit=self):
        #     if mgr.member.pk not in ids:
        #         ids.append(mgr.member.pk)
        # if ids:
        #     return User.objects.filter(pk__in=ids)
        # else:
        #     return User.objects.none()

    def get_absolute_url(self):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
            self.save()
        return reverse("organisationalunit_detail", kwargs={"slug": self.slug})

    def get_avatar_url(self):
        if self.image:
            return self.image.url
        else:
            rand = random.randint(1, 5)
            return static("assets/img/team-{}.jpg".format(rand))

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
        super().save(*args, **kwargs)
        # Resync permissions...
        self.sync_permissions()


class OrganisationalUnitRole(models.Model):
    name = models.CharField(verbose_name="Name", max_length=255, unique=True)
    bs_colour = models.CharField(
        verbose_name="Bootstrap Colour", max_length=255, default="info"
    )
    default_role = models.BooleanField("Default Role", default=False)
    manage_role = models.BooleanField("Manager Role", default=False)
    permissions = models.ManyToManyField(Permission)
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        ordering = [
            "name",
        ]

    def sync_default_permissions(self):
        for role in UnitRoles.DEFAULTS:
            if self.pk == role["pk"]:
                self.permissions.clear()
                for perm in UnitRoles.PERMISSIONS[role["pk"]][1]:
                    if perm:
                        codeword = perm
                        if "." in perm:
                            codeword = perm.split(".")[1]
                        if Permission.objects.filter(codename=codeword).exists():
                            permission = Permission.objects.get(codename=codeword)
                            self.permissions.add(permission)
                self.save()
                return True

        # If we reach this; this role isn't matched in code
        return False


class OrganisationalUnitMember(models.Model):
    unit = models.ForeignKey(
        OrganisationalUnit, on_delete=models.CASCADE, related_name="members"
    )
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="unit_memberships",
        on_delete=models.CASCADE,
    )
    inviter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET(get_sentinel_user),
        related_name="unitmember_invites",
        null=True,
        blank=True,
    )
    roles = models.ManyToManyField(
        OrganisationalUnitRole, verbose_name="Roles", blank=True
    )
    add_date = models.DateTimeField(
        verbose_name="Date Added",
        help_text="Date the user was added to the unit",
        auto_now_add=True,
    )
    mod_date = models.DateTimeField(
        verbose_name="Date Modified",
        help_text="Last date the membership was modified",
        auto_now=True,
    )
    left_date = models.DateTimeField(
        verbose_name="Date Left",
        help_text="Date the user left the group",
        null=True,
        blank=True,
    )
    history = HistoricalRecords()

    class Meta:
        ordering = [
            "member",
        ]
        unique_together = [
            "unit", "member",
        ]
        get_latest_by = "mod_date"

    def getActiveRoles(self):
        return OrganisationalUnitMember.objects.filter(
            unit=self.unit,
            member=self.member,
            left_date__isnull=True,
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Lets resync the permissions!
        self.unit.sync_permissions()
