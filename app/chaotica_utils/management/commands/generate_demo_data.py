import random
import string
from datetime import datetime, timedelta, date
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from faker import Faker

from chaotica_utils.models import JobLevel
from jobtracker.models import (
    Job, Phase, Client, Service, Skill, SkillCategory, TimeSlot, TimeSlotType,
    OrganisationalUnit, OrganisationalUnitMember, OrganisationalUnitRole,
    Contact, BillingCode, UserSkill, FrameworkAgreement, Feedback
)
from jobtracker.enums import PhaseStatuses, FeedbackType, TechQARatings, PresQARatings, UserSkillRatings
from chaotica_utils.models import LeaveRequest, UserCost
from notifications.models import NotificationSubscription

User = get_user_model()
fake = Faker()


class Command(BaseCommand):
    help = 'Generates demo data for CHAOTICA system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before generating new data',
        )
        parser.add_argument(
            '--users',
            type=int,
            default=20,
            help='Number of users to create (default: 20)',
        )
        parser.add_argument(
            '--clients',
            type=int,
            default=10,
            help='Number of clients to create (default: 10)',
        )
        parser.add_argument(
            '--jobs',
            type=int,
            default=100,
            help='Number of jobs to create (default: 100)',
        )
        parser.add_argument(
            '--minimal',
            action='store_true',
            help='Create minimal dataset for quick testing',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting demo data generation...'))

        if options['minimal']:
            options['users'] = 5
            options['clients'] = 3
            options['jobs'] = 10

        if options['clear']:
            self.clear_existing_data()

        self.create_organisational_units()
        self.create_job_levels()
        self.create_skills()
        self.create_services()
        self.create_timeslot_types()
        self.create_users(options['users'])
        self.create_clients(options['clients'])
        self.create_jobs_and_phases(options['jobs'])
        self.create_timeslots()
        self.create_leave_requests()

        self.stdout.write(self.style.SUCCESS('Demo data generation completed successfully!'))

    def clear_existing_data(self):
        self.stdout.write('Clearing existing data...')
        models_to_clear = [
            TimeSlot, TimeSlotType, Phase, Job, FrameworkAgreement, Contact, Client,
            UserSkill, UserCost, LeaveRequest, Service, Skill,
            OrganisationalUnitMember, OrganisationalUnit, JobLevel
        ]
        for model in models_to_clear:
            model.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()

    def create_organisational_units(self):
        self.stdout.write('Creating organisational units...')

        self.units = []
        unit_data = [
            ('United Kingdom', 'UK', 'UK security testing team', '09:00', '17:30', 'Europe/London'),
            ('Germany', 'DE', 'German security testing team', '09:00', '17:30', 'Europe/Berlin'),
            ('United States', 'US', 'US security testing team', '09:00', '17:00', 'US/Eastern'),
            ('Australia', 'AU', 'Australian security testing team', '09:00', '17:30', 'Australia/Sydney'),
            ('Netherlands', 'NL', 'Netherlands security testing team', '09:00', '17:30', 'Europe/Amsterdam'),
        ]

        for name, short, desc, start_time, end_time, timezone_name in unit_data:
            unit = OrganisationalUnit.objects.create(
                name=name,
                slug=short,
                description=desc,
                businessHours_startTime=start_time,
                businessHours_endTime=end_time,
                businessHours_days='1,2,3,4,5',
                # lunchHours_startTime='12:00',
                # lunchHours_endTime='13:00',
                # lunchHours_days='1,2,3,4,5'
            )
            self.units.append(unit)

    def create_job_levels(self):
        self.stdout.write('Creating job levels...')

        self.job_levels = []
        levels = [
            ('Junior', 'Junior Consultant', 1),
            ('Consultant', 'Consultant', 2),
            ('Senior', 'Senior Consultant', 3),
            ('Principal', 'Principal Consultant', 4),
            ('Managing', 'Managing Consultant', 5),
            ('Director', 'Director', 6),
        ]

        for short_label, name, order in levels:
            level = JobLevel.objects.create(short_label=short_label, long_label=name, order=order)
            self.job_levels.append(level)

    def create_skills(self):
        self.stdout.write('Creating skills...')

        self.skills = []
        skill_categories = {
            'Technical': [
                'Web Application Testing', 'Network Penetration Testing',
                'Mobile Application Testing', 'API Testing', 'Cloud Security',
                'Active Directory', 'Wireless Testing', 'Social Engineering',
                'Binary Exploitation', 'Cryptography Analysis'
            ],
            'Tools': [
                'Burp Suite', 'Metasploit', 'Nmap', 'Wireshark', 'Kali Linux',
                'Cobalt Strike', 'BloodHound', 'PowerShell', 'Python Scripting',
                'AWS Security Tools', 'Azure Security Center'
            ],
            'Methodologies': [
                'OWASP Testing Guide', 'PTES', 'MITRE ATT&CK', 'Kill Chain',
                'NIST Cybersecurity Framework', 'ISO 27001', 'PCI DSS'
            ],
            'Soft Skills': [
                'Report Writing', 'Client Communication', 'Project Management',
                'Team Leadership', 'Technical Mentoring', 'Presentation Skills'
            ]
        }

        for category, skill_list in skill_categories.items():
            cat, _ = SkillCategory.objects.get_or_create(name=category)
            for skill_name in skill_list:
                skill = Skill.objects.create(
                    name=skill_name,
                    category=cat,
                    description=f'{skill_name} expertise'
                )
                self.skills.append(skill)

    def create_services(self):
        self.stdout.write('Creating services...')

        self.services = []
        service_data = [
            ('Infrastructure Penetration Test', 'Network and infrastructure security assessment', True),
            ('Web Application Security Assessment', 'Comprehensive web application testing', True),
            ('Mobile Application Security Review', 'iOS and Android application testing', True),
            ('Red Team Exercise', 'Full adversarial simulation', True),
            ('Purple Team Exercise', 'Collaborative attack and defense', False),
            ('Cloud Security Assessment', 'AWS/Azure/GCP security review', True),
            ('Wireless Security Assessment', 'WiFi and wireless protocol testing', False),
            ('Social Engineering Assessment', 'Physical and digital social engineering', False),
            ('Security Architecture Review', 'Design and architecture security analysis', True),
            ('Code Review', 'Static application security testing', True),
            ('DevSecOps Consulting', 'CI/CD pipeline security integration', False),
            ('Incident Response Readiness', 'IR capability assessment', False),
        ]

        for name, desc, is_core in service_data:
            service = Service.objects.create(
                name=name,
                description=desc,
                is_core=is_core
            )
            num_skills = random.randint(3, 8)
            required_skills = random.sample(self.skills, min(num_skills, len(self.skills)))
            service.skillsRequired.set(required_skills[:num_skills//2])
            service.skillsDesired.set(required_skills[num_skills//2:])
            self.services.append(service)

    def create_timeslot_types(self):
        self.stdout.write('Creating timeslot types...')

        self.timeslot_types = []
        types = [
            ('Client Delivery', True, '#28a745'),
            ('Internal Project', False, '#17a2b8'),
            ('Training', False, '#ffc107'),
            ('Annual Leave', False, '#6c757d'),
            ('Sick Leave', False, '#dc3545'),
            ('Admin', False, '#6610f2'),
        ]

        for name, deliverable, color in types:
            ts_type = TimeSlotType.objects.create(
                name=name,
                is_delivery=deliverable,
            )
            self.timeslot_types.append(ts_type)

    def create_users(self, count):
        self.stdout.write(f'Creating {count} users...')

        self.users = []

        region_data = {
            'UK': {
                'locations': ['London', 'Manchester', 'Edinburgh', 'Birmingham'],
                'timezone': 'Europe/London'
            },
            'DE': {
                'locations': ['Berlin', 'Munich', 'Hamburg', 'Frankfurt'],
                'timezone': 'Europe/Berlin'
            },
            'US': {
                'locations': ['New York', 'Chicago', 'Los Angeles', 'Remote'],
                'timezone': 'US/Eastern'
            },
            'AU': {
                'locations': ['Sydney', 'Melbourne', 'Brisbane', 'Perth'],
                'timezone': 'Australia/Sydney'
            },
            'NL': {
                'locations': ['Amsterdam', 'Rotterdam', 'The Hague', 'Utrecht'],
                'timezone': 'Europe/Amsterdam'
            }
        }

        for i in range(count):
            first_name = fake.first_name()
            last_name = fake.last_name()
            email = f"{first_name.lower()}.{last_name.lower()}@chaotica-demo.com"

            unit = random.choice(self.units)
            region_short = unit.slug
            region_info = region_data.get(region_short, region_data['UK'])

            user, _ = User.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'password': 'DemoPass123!',
                    'job_title': random.choice([jl.long_label for jl in self.job_levels]),
                    'location': random.choice(region_info['locations']),
                    'country': region_short,
                    'pref_timezone': region_info['timezone'],
                    'contracted_leave': 25,
                    'carry_over_leave': random.randint(0, 5)
                }
            )

            role, _ = OrganisationalUnitRole.objects.get_or_create(
                name='Member',
            )
            member = OrganisationalUnitMember.objects.create(
                member=user,
                unit=unit,
            )
            member.roles.add(role)
            member.save()

            if i > 0 and i % 5 != 0:
                user.manager = random.choice(self.users[:max(1, i//5)])
                user.save()

            num_skills = random.randint(5, 15)
            for skill in random.sample(self.skills, min(num_skills, len(self.skills))):
                UserSkill.objects.create(
                    user=user,
                    skill=skill,
                    rating=random.choice(UserSkillRatings.CHOICES)[0]
                )

            if random.random() > 0.3:
                user.job_level = random.choice(self.job_levels)
                user.save()

            self.users.append(user)

        if self.units and self.users:
            for unit in self.units:
                unit.lead = random.choice(self.users)
                unit.save()

    def create_clients(self, count):
        self.stdout.write(f'Creating {count} clients...')

        self.clients = []
        industries = ['Financial Services', 'Healthcare', 'Technology', 'Retail', 'Government', 'Energy']

        for i in range(count):
            company_name = fake.company()
            client = Client.objects.create(
                name=company_name,
                short_name=''.join([w[0].upper() for w in company_name.split()][:3]),
                hours_in_day=random.choice([7.5, 8.0])
            )

            num_ams = random.randint(1, 3)
            client.account_managers.set(random.sample(self.users, min(num_ams, len(self.users))))

            for j in range(random.randint(1, 4)):
                Contact.objects.create(
                    client=client,
                    name=fake.name(),
                    email=fake.company_email(),
                    job_title=random.choice(['CISO', 'Security Manager', 'IT Director', 'CTO'])
                )

            if random.random() > 0.3:
                FrameworkAgreement.objects.create(
                    client=client,
                    title=f'{company_name} Master Services Agreement',
                    value=Decimal(random.randint(50000, 500000)),
                    start_date=timezone.now().date() - timedelta(days=random.randint(30, 365)),
                    end_date=timezone.now().date() + timedelta(days=random.randint(90, 730)),
                    is_active=True
                )

            self.clients.append(client)

    def create_jobs_and_phases(self, count):
        self.stdout.write(f'Creating {count} jobs with phases...')

        self.jobs = []
        self.phases = []

        three_months_ago = timezone.now().date() - timedelta(days=90)
        today = timezone.now().date()

        security_services = [
            'Infrastructure Penetration Test', 'Web Application Security Assessment',
            'Mobile Application Security Review', 'Red Team Exercise',
            'Cloud Security Assessment', 'Security Architecture Review'
        ]

        for i in range(count):
            client = random.choice(self.clients)

            job_start_date = fake.date_between(start_date=three_months_ago, end_date=today - timedelta(days=30))
            job_duration = random.randint(10, 45)
            job_end_date = job_start_date + timedelta(days=job_duration)

            assessment_quarter = self.get_quarter_from_date(job_start_date)

            job = Job.objects.create(
                title=f'{client.name} - {assessment_quarter} {random.choice(security_services)}',
                overview=fake.paragraph(nb_sentences=random.randint(2, 4)),
                client=client,
                unit=random.choice(self.units),
                account_manager=random.choice(list(client.account_managers.all()) + self.users[:5]),
                desired_start_date=job_start_date,
                desired_delivery_date=job_end_date,
                revenue=Decimal(random.randint(15000, 200000)),
                status='DRAFT'
            )

            job.scoped_by.set(random.sample(self.users, min(random.randint(2, 4), len(self.users))))

            billing_code = BillingCode.objects.create(
                name=f'BC-{job.id:05d}',
                code=f'{job.id:05d}',
                job=job,
                is_visible=True
            )
            job.charge_codes.add(billing_code)

            num_phases = random.randint(1, 3)
            current_phase_date = job_start_date

            for p in range(num_phases):
                service = random.choice(self.services)
                phase_duration = random.randint(5, 15)

                phase = Phase.objects.create(
                    job=job,
                    phase_number=p + 1,
                    title=f'Phase {p + 1}: {service.name}',
                    service=service,
                    status=PhaseStatuses.PENDING,
                    project_lead=random.choice(self.users),
                    report_author=random.choice(self.users),
                    delivery_hours=random.randint(16, 80),
                    reporting_hours=random.randint(8, 32),
                    mgmt_hours=random.randint(4, 16),
                    qa_hours=random.randint(4, 12),
                    contingency_hours=random.randint(0, 8),
                    start_date_type='SPECIFIC',
                    desired_start_date=current_phase_date,
                    desired_delivery_date=current_phase_date + timedelta(days=phase_duration),
                    feedback_scope_correct=None
                )

                consultants = random.sample(self.users, min(random.randint(2, 5), len(self.users)))
                phase.consultants_allocated.set(consultants)

                if random.random() > 0.3:
                    phase.techqa_by = random.choice([u for u in self.users if u not in consultants])
                if random.random() > 0.3:
                    phase.presqa_by = random.choice([u for u in self.users if u not in consultants])

                phase.save()
                self.phases.append(phase)

                current_phase_date += timedelta(days=phase_duration + random.randint(1, 5))

            self.progress_job_workflow(job)
            self.jobs.append(job)

    def get_quarter_from_date(self, date_obj):
        month = date_obj.month
        if month <= 3:
            return 'Q1'
        elif month <= 6:
            return 'Q2'
        elif month <= 9:
            return 'Q3'
        else:
            return 'Q4'

    def progress_job_workflow(self, job):
        phases = job.phases.all().order_by('phase_number')

        for phase in phases:

            if phase.desired_delivery_date < timezone.now().date() - timedelta(days=7):
                self.progress_phase_to_completion(phase)
            elif phase.desired_delivery_date < timezone.now().date() + timedelta(days=7):
                self.progress_phase_partially(phase)
            else:
                status_choice = random.choice([
                    PhaseStatuses.PENDING, PhaseStatuses.SCOPING, PhaseStatuses.SCOPED,
                    PhaseStatuses.PENDING_SCHED, PhaseStatuses.SCHEDULED
                ])
                phase.status = status_choice
                if status_choice >= PhaseStatuses.SCOPED:
                    phase.feedback_scope_correct = random.choice([True, True, True, False])
                phase.save()

        job_phases = list(phases)
        if job_phases:
            max_phase_status = max(p.status for p in job_phases)
            if max_phase_status >= PhaseStatuses.COMPLETE:
                job.status = 'COMPLETED'
            elif max_phase_status >= PhaseStatuses.IN_PROGRESS:
                job.status = 'IN_PROGRESS'
            elif max_phase_status >= PhaseStatuses.SCHEDULED:
                job.status = 'SCHEDULED'
            elif max_phase_status >= PhaseStatuses.SCOPED:
                job.status = 'SCOPED'
            else:
                job.status = random.choice(['DRAFT', 'SCOPING'])
            job.save()

    def progress_phase_to_completion(self, phase):

        phase.status = PhaseStatuses.COMPLETE
        phase.feedback_scope_correct = True

        if phase.techqa_by:
            phase.techqa_report_rating = random.choice([
                TechQARatings.NEEDS_WORK, TechQARatings.GOOD,
                TechQARatings.GOOD, TechQARatings.EXCELLENT
            ])

        if phase.presqa_by:
            phase.presqa_report_rating = random.choice([
                PresQARatings.NEEDS_WORK, PresQARatings.GOOD,
                PresQARatings.GOOD, PresQARatings.EXCELLENT
            ])

        phase.save()

        self.create_phase_feedback(phase)

    def progress_phase_partially(self, phase):

        status_options = [
            PhaseStatuses.SCOPED, PhaseStatuses.SCHEDULED, PhaseStatuses.IN_PROGRESS,
            PhaseStatuses.REPORTING, PhaseStatuses.PENDING_TQA, PhaseStatuses.QA_TECH,
            PhaseStatuses.PENDING_PQA, PhaseStatuses.QA_PRES
        ]

        phase.status = random.choice(status_options)

        if phase.status >= PhaseStatuses.SCOPED:
            phase.feedback_scope_correct = random.choice([True, True, True, False])

        if phase.status >= PhaseStatuses.QA_TECH and phase.techqa_by:
            phase.techqa_report_rating = random.choice([
                TechQARatings.NEEDS_WORK, TechQARatings.GOOD, TechQARatings.EXCELLENT
            ])

        if phase.status >= PhaseStatuses.QA_PRES and phase.presqa_by:
            phase.presqa_report_rating = random.choice([
                PresQARatings.NEEDS_WORK, PresQARatings.GOOD, PresQARatings.EXCELLENT
            ])

        phase.save()

        if phase.status >= PhaseStatuses.QA_TECH:
            self.create_phase_feedback(phase)

    def create_phase_feedback(self, phase):

        if phase.status >= PhaseStatuses.QA_TECH and phase.techqa_by:
            tech_feedback_texts = [
                "Technical approach was sound. Good coverage of attack vectors. Minor formatting issues in findings section.",
                "Excellent technical depth. All major vulnerabilities identified and well documented. Clear remediation guidance provided.",
                "Some gaps in testing methodology. Missing validation of fixes. Executive summary needs improvement.",
                "Comprehensive assessment with good technical detail. Well structured report with clear risk ratings.",
                "Testing was thorough but report lacks technical depth in some findings. Risk scoring inconsistent."
            ]

            Feedback.objects.create(
                author=phase.techqa_by,
                phase=phase,
                feedbackType=FeedbackType.TECH,
                body=random.choice(tech_feedback_texts)
            )

        if phase.status >= PhaseStatuses.QA_PRES and phase.presqa_by:
            pres_feedback_texts = [
                "Report structure is clear and professional. Executive summary effectively communicates key risks to business stakeholders.",
                "Excellent presentation quality. Findings are well articulated with appropriate business context. Ready for client delivery.",
                "Some formatting inconsistencies noted. Risk ratings need better justification. Overall content is solid.",
                "Professional presentation with good flow. Technical findings translated well for business audience.",
                "Report quality is good but could benefit from more detailed recommendations section. Client-ready with minor edits."
            ]

            Feedback.objects.create(
                author=phase.presqa_by,
                phase=phase,
                feedbackType=FeedbackType.PRES,
                body=random.choice(pres_feedback_texts)
            )

        if random.random() > 0.7:
            scope_feedback_texts = [
                "Initial scope was appropriate and well defined. All objectives met.",
                "Scope expanded during engagement to include additional systems. Client was satisfied with coverage.",
                "Limited scope due to client constraints. Recommended follow-up assessment for remaining systems.",
                "Comprehensive scope allowed for thorough assessment. Good collaboration with client technical team."
            ]

            Feedback.objects.create(
                author=random.choice([phase.project_lead, phase.report_author]),
                phase=phase,
                feedbackType=FeedbackType.SCOPE,
                body=random.choice(scope_feedback_texts)
            )

    def create_timeslots(self):
        self.stdout.write('Creating timeslots...')

        delivery_type = next((t for t in self.timeslot_types if t.is_delivery), None)
        if not delivery_type:
            return

        phases_with_activity = Phase.objects.filter(
            status__in=[
                PhaseStatuses.SCHEDULED, PhaseStatuses.IN_PROGRESS, PhaseStatuses.REPORTING,
                PhaseStatuses.PENDING_TQA, PhaseStatuses.QA_TECH, PhaseStatuses.PENDING_PQA,
                PhaseStatuses.QA_PRES, PhaseStatuses.COMPLETE
            ]
        )

        for phase in phases_with_activity:
            consultants = list(phase.consultants_allocated.all())
            if not consultants or not phase.desired_start_date:
                continue

            phase_start = phase.desired_start_date
            phase_end = phase.desired_delivery_date or (phase_start + timedelta(days=10))

            if phase.status >= PhaseStatuses.COMPLETE:
                delivery_end = phase_end
            elif phase.status >= PhaseStatuses.REPORTING:
                delivery_end = phase_end - timedelta(days=2)
            elif phase.status >= PhaseStatuses.IN_PROGRESS:
                delivery_end = min(timezone.now().date(), phase_end - timedelta(days=1))
            else:
                continue

            current_date = phase_start
            total_hours_needed = phase.delivery_hours + phase.reporting_hours + phase.mgmt_hours

            hours_allocated = 0
            day_count = 0

            while current_date <= delivery_end and hours_allocated < total_hours_needed and day_count < 30:
                if current_date.weekday() >= 5:
                    current_date += timedelta(days=1)
                    continue

                num_consultants_today = random.randint(1, min(3, len(consultants)))
                consultants_today = random.sample(consultants, num_consultants_today)

                for consultant in consultants_today:
                    if random.random() > 0.8:
                        continue

                    hours_today = random.choice([4, 6, 7, 7.5, 8])

                    start_hour = random.choice([8, 9, 10])
                    start_time = timezone.make_aware(
                        datetime.combine(current_date, datetime.strptime(f'{start_hour:02d}:00', '%H:%M').time())
                    )
                    end_time = start_time + timedelta(hours=hours_today)

                    if phase.status >= PhaseStatuses.REPORTING:
                        role = random.choice(['REPORTING', 'REPORTING', 'DELIVERY', 'QA'])
                    elif phase.status >= PhaseStatuses.IN_PROGRESS:
                        role = random.choice(['DELIVERY', 'DELIVERY', 'DELIVERY', 'MANAGEMENT'])
                    else:
                        role = 'DELIVERY'

                    is_onsite = False
                    if phase.service and 'Infrastructure' in phase.service.name:
                        is_onsite = random.random() > 0.6
                    elif phase.service and 'Red Team' in phase.service.name:
                        is_onsite = random.random() > 0.4

                    TimeSlot.objects.create(
                        user=consultant,
                        phase=phase,
                        slot_type=delivery_type,
                        start=start_time,
                        end=end_time,
                        deliveryRole=role,
                        is_onsite=is_onsite
                    )

                    hours_allocated += hours_today

                current_date += timedelta(days=1)
                day_count += 1

            if phase.status >= PhaseStatuses.QA_TECH and phase.techqa_by:
                self.create_qa_timeslots(phase, phase.techqa_by, 'QA', qa_type='Tech')

            if phase.status >= PhaseStatuses.QA_PRES and phase.presqa_by:
                self.create_qa_timeslots(phase, phase.presqa_by, 'QA', qa_type='Pres')

    def create_qa_timeslots(self, phase, qa_user, role, qa_type='Tech'):
        delivery_type = next((t for t in self.timeslot_types if t.is_delivery), None)
        if not delivery_type or not phase.desired_delivery_date:
            return

        qa_start = phase.desired_delivery_date + timedelta(days=1)

        if qa_type == 'Pres':
            qa_start += timedelta(days=2)

        qa_hours_needed = random.randint(2, 6)
        hours_per_day = random.choice([2, 3, 4])

        current_date = qa_start
        hours_allocated = 0

        while hours_allocated < qa_hours_needed and current_date <= qa_start + timedelta(days=7):
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue

            start_time = timezone.make_aware(
                datetime.combine(current_date, datetime.strptime('10:00', '%H:%M').time())
            )
            end_time = start_time + timedelta(hours=hours_per_day)

            TimeSlot.objects.create(
                user=qa_user,
                phase=phase,
                slot_type=delivery_type,
                start=start_time,
                end=end_time,
                deliveryRole=role,
                is_onsite=False
            )

            hours_allocated += hours_per_day
            current_date += timedelta(days=1)

    def create_leave_requests(self):
        self.stdout.write('Creating leave requests...')

        leave_types = ['annual', 'sick', 'unpaid', 'other']

        for user in random.sample(self.users, min(len(self.users) // 2, len(self.users))):
            num_requests = random.randint(1, 3)

            for _ in range(num_requests):
                start = timezone.now().date() + timedelta(days=random.randint(-30, 90))
                end = start + timedelta(days=random.randint(1, 10))

                leave = LeaveRequest.objects.create(
                    user=user,
                    start_date=start,
                    end_date=end,
                    type_of_leave=random.choice(leave_types),
                    notes=fake.sentence() if random.random() > 0.5 else '',
                    authorised=random.random() > 0.3
                )

                if leave.authorised and user.manager:
                    leave.authorised_by = user.manager
                    leave.save()

                    leave_type = next((t for t in self.timeslot_types if 'LEAVE' in t.short_name), None)
                    if leave_type:
                        current = start
                        while current <= end:
                            if current.weekday() < 5:
                                start_time = timezone.make_aware(
                                    datetime.combine(current, datetime.strptime('09:00', '%H:%M').time())
                                )
                                end_time = start_time + timedelta(hours=7.5)

                                ts = TimeSlot.objects.create(
                                    user=user,
                                    slot_type=leave_type,
                                    start=start_time,
                                    end=end_time
                                )
                                leave.timeslot = ts
                                leave.save()
                                break
                            current += timedelta(days=1)