from django.db import models
from django.conf import settings
from django.utils.text import slugify
from django.urls import reverse
from simple_history.models import HistoricalRecords
from guardian.shortcuts import assign_perm, remove_perm, get_user_perms, get_users_with_perms
from django.db.models import JSONField
import uuid, os, random
from chaotica_utils.models import User
from chaotica_utils.enums import UnitRoles
from decimal import Decimal
from django.templatetags.static import static
from django_bleach.models import BleachField


def _default_business_days():
    return [1,2,3,4,5]


def get_media_image_file_path(instance, filename):
    ext = filename.split('.')[-1]
    filename = "%s.%s" % (uuid.uuid4(), ext)
    return os.path.join('media/images', filename)


class OrganisationalUnit(models.Model):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(null=False, default='', unique=True)
    description = BleachField(default="", null=True)
    image = models.ImageField(default='default.jpg',  
                                     upload_to=get_media_image_file_path)
    targetProfit = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal(37),
        verbose_name="Target Profit", help_text="The % target profit for this unit")
    businessHours_startTime = models.TimeField('Start Time', default='09:00:00')
    businessHours_endTime = models.TimeField('End Time', default='17:30:00')
    businessHours_days = JSONField(verbose_name="Days", null=True, blank=True, default=_default_business_days, help_text="An int array with the numbers equaling the day of the week. Sunday == 0, Monday == 2 etc")
    approval_required = models.BooleanField('Approval Required', default=True, help_text="Approval by a Manager is required to join the unit")
    special_requirements = BleachField(blank=True, null=True)
    history = HistoricalRecords()
    lead = models.ForeignKey(settings.AUTH_USER_MODEL,
                            related_name='units_lead',
                            default=1,
                            on_delete=models.CASCADE)

    class Meta:
        ordering = ['name']
        permissions = (
            ('manage_members', 'Assign Members'),
            ('can_view_unit_jobs', 'Can view jobs'),
            ('can_add_job', 'Can add jobs'),
            ('can_view_all_leave_requests', 'Can view all leave for members of the unit'),
            ('can_approve_leave_requests', 'Can approve leave requests'),

            ('can_tqa_jobs', 'Can TQA jobs'),
            ('can_pqa_jobs', 'Can PQA jobs'),

            ('can_scope_jobs', 'Can scope jobs'),
            ('can_signoff_scopes', 'Can signoff scopes'),
            ('can_signoff_own_scopes', 'Can signoff own scopes'),

            ('view_users_schedule', 'View Members Schedule'),
            ('can_schedule_phases', 'Can schedule phases'),
        )
    
    def syncPermissions(self):
        from pprint import pprint
        for user in self.get_allMembers():
            # Ensure the permissions are set right!
            existing_perms = list(get_user_perms(user, self).values_list('codename', flat=True))

            expected_perms = []
            # get a combined list of perms from their roles...
            for ms in OrganisationalUnitMember.objects.filter(unit=self, member=user, left_date__isnull=True):
                for role_perm in UnitRoles.PERMISSIONS[ms.role][1]:
                    if "." in role_perm:
                        clean_perm = role_perm.split('.')[1]
                    else:
                        clean_perm = role_perm
                    if clean_perm not in expected_perms:
                        expected_perms.append(clean_perm)

            if expected_perms:
                # First lets add missing perms...
                for new_perm in expected_perms:
                    if new_perm not in existing_perms:
                        # pprint("Add new perm: "+str(new_perm))
                        assign_perm(new_perm, user, self)
                
                # Now lets remove old perms
                for old_perm in existing_perms:
                    if old_perm not in expected_perms:
                        # pprint("Remove old perm: "+str(old_perm))
                        remove_perm(old_perm, user, self)
            else:
                if existing_perms:
                    # We should not have any permissions! Clear them all
                    for perm in existing_perms:
                        # pprint("Clear old perm: "+str(perm))
                        remove_perm(perm, user, self)
    

    def __str__(self):
        return self.name    
          
    def get_managers(self):
        ids = []
        for mgr in OrganisationalUnitMember.objects.filter(unit=self, role=UnitRoles.MANAGER):
            if mgr.member.pk not in ids:
                ids.append(mgr.member.pk)
        if ids:
            return User.objects.filter(pk__in=ids)
        else:
            return User.objects.none()
          
    def get_activeMembers(self):
        ids = []
        for mgr in OrganisationalUnitMember.objects.filter(unit=self, left_date__isnull=True):
            if mgr.member.pk not in ids:
                ids.append(mgr.member.pk)
        if ids:
            return User.objects.filter(pk__in=ids)
        else:
            return User.objects.none()
          
    def get_active_members_with_perm(self, permission_str, include_su=False):
        members = self.get_activeMembers()
        return get_users_with_perms(self, with_superusers=include_su, only_with_perms_in=[permission_str]).filter(pk__in=members).distinct()
          
    def get_allMembers(self):
        ids = []
        for mgr in OrganisationalUnitMember.objects.filter(unit=self):
            if mgr.member.pk not in ids:
                ids.append(mgr.member.pk)
        if ids:
            return User.objects.filter(pk__in=ids)
        else:
            return User.objects.none()
        
    def get_absolute_url(self):
        if not self.slug:
            self.slug = slugify(self.name)
            self.save()
        return reverse('organisationalunit_detail', kwargs={"slug": self.slug})
    
    def get_avatar_url(self):
        if self.image:
            return self.image.url
        else:
            rand = random.randint(1,5)
            return static('assets/img/team-{}.jpg'.format(rand))

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
        # Resync permissions...
        self.syncPermissions()


class OrganisationalUnitMember(models.Model):
    unit = models.ForeignKey(OrganisationalUnit, on_delete=models.CASCADE, related_name='members')
    member = models.ForeignKey(settings.AUTH_USER_MODEL,
                               related_name='unit_memberships',
                               on_delete=models.CASCADE)
    inviter = models.ForeignKey(settings.AUTH_USER_MODEL,
                                on_delete=models.CASCADE,
                                related_name="unitmember_invites",
                                null=True,
                                blank=True)
    role = models.IntegerField(verbose_name="Role",
                        choices=UnitRoles.CHOICES, default=UnitRoles.CONSULTANT)
    add_date = models.DateTimeField(verbose_name="Date Added", help_text="Date the user was added to the unit", auto_now_add=True)
    mod_date = models.DateTimeField(verbose_name="Date Modified", help_text="Last date the membership was modified", auto_now=True)
    left_date = models.DateTimeField(verbose_name="Date Left", help_text="Date the user left the group", null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ['member', '-role']
        get_latest_by = 'mod_date'
        
    @property
    def role_bs_colour(self):
        return UnitRoles.BS_COLOURS[self.role][1]
    
    def getActiveRoles(self):
        return OrganisationalUnitMember.objects.filter(
            unit=self.unit, member=self.member,
            left_date__isnull=True,
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Lets resync the permissions!
        self.unit.syncPermissions()