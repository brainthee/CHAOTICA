# Setup wizard views
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.contrib import messages
from django.contrib.auth import login
from django.views.generic import View
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.db import transaction

from chaotica_utils.models import User
from chaotica_utils.wizard_steps import (
    WizardUserForm,
    WizardOrganisationForm,
    WizardServiceForm,
    WizardSkillForm,
    WizardClientForm
)


class SetupWizardView(View):
    """Multi-step setup wizard for initial CHAOTICA configuration"""

    template_base = 'wizard/'
    steps = [
        'welcome',
        'admin_user',
        'organisation',
        'services',
        'skills',
        'clients',
        'complete'
    ]

    @method_decorator(never_cache)
    @method_decorator(csrf_protect)
    def dispatch(self, *args, **kwargs):
        # Check if setup is already done - must have ALL essential components
        from jobtracker.models import OrganisationalUnit, Service, SkillCategory, Client

        setup_complete = (
            User.objects.count() > 0 and
            OrganisationalUnit.objects.count() > 0 and
            Service.objects.count() > 0 and
            SkillCategory.objects.count() > 0 and
            Client.objects.count() > 0
        )

        if setup_complete:
            messages.warning(self.request, "Setup wizard has already been completed.")
            return redirect('dashboard')
        return super().dispatch(*args, **kwargs)

    def get(self, request):
        step = request.GET.get('step', None)

        # If no step specified, determine where we should be
        if not step:
            step = self.determine_current_step(request)

        if step not in self.steps:
            step = 'welcome'

        # Only clear session if explicitly on welcome and nothing exists yet
        if step == 'welcome' and not self.has_existing_data():
            request.session.pop('wizard_data', None)

        context = self.get_context(request, step)
        return render(request, f"{self.template_base}{step}.html", context)

    def post(self, request):
        step = request.POST.get('current_step', 'welcome')

        if step == 'welcome':
            return redirect(f'{request.path}?step=admin_user')

        elif step == 'admin_user':
            return self.handle_admin_user(request)

        elif step == 'organisation':
            return self.handle_organisation(request)

        elif step == 'services':
            return self.handle_services(request)

        elif step == 'skills':
            return self.handle_skills(request)

        elif step == 'clients':
            return self.handle_clients(request)

        return redirect('dashboard')

    def get_context(self, request, step):
        """Get context data for the current step"""
        wizard_data = request.session.get('wizard_data', {})
        context = {
            'current_step': step,
            'steps': self.steps,
            'step_index': self.steps.index(step),
            'total_steps': len(self.steps),
            'wizard_data': wizard_data,
            'progress_percent': (self.steps.index(step) / len(self.steps)) * 100,
        }

        if step == 'admin_user':
            context['form'] = WizardUserForm()

        elif step == 'organisation':
            user_id = wizard_data.get('admin_user_id')
            user = User.objects.get(pk=user_id) if user_id else None
            context['form'] = WizardOrganisationForm(user=user)

        elif step == 'services':
            context['form'] = WizardServiceForm()

        elif step == 'skills':
            context['form'] = WizardSkillForm()

        elif step == 'clients':
            context['form'] = WizardClientForm()

        elif step == 'complete':
            # Summary of what was created
            context['summary'] = self.get_summary(wizard_data)

        return context

    @transaction.atomic
    def handle_admin_user(self, request):
        """Handle admin user creation"""
        # Check if admin user already exists
        if User.objects.filter(is_superuser=True).exists():
            # Skip to next step if admin already exists
            user = User.objects.filter(is_superuser=True).first()
            wizard_data = request.session.get('wizard_data', {})
            wizard_data['admin_user_id'] = user.pk
            wizard_data['admin_user_name'] = f"{user.first_name} {user.last_name}"
            request.session['wizard_data'] = wizard_data

            if not request.user.is_authenticated:
                # Log the user in if not already
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')

            messages.info(request, "Admin user already exists, continuing setup...")
            return redirect(f'{request.path}?step=organisation')

        form = WizardUserForm(request.POST)

        if form.is_valid():
            user = form.save(commit=False)
            user.is_staff = True
            user.is_superuser = True
            user.save()

            # Store in session
            wizard_data = request.session.get('wizard_data', {})
            wizard_data['admin_user_id'] = user.pk
            wizard_data['admin_user_name'] = f"{user.first_name} {user.last_name}"
            request.session['wizard_data'] = wizard_data

            # Log the user in
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')

            messages.success(request, f"Admin user '{user.email}' created successfully!")
            return redirect(f'{request.path}?step=organisation')

        context = self.get_context(request, 'admin_user')
        context['form'] = form
        return render(request, f"{self.template_base}admin_user.html", context)

    @transaction.atomic
    def handle_organisation(self, request):
        """Handle organisation unit creation"""
        from jobtracker.models import OrganisationalUnit, OrganisationalUnitMember, OrganisationalUnitRole

        wizard_data = request.session.get('wizard_data', {})
        user_id = wizard_data.get('admin_user_id')
        user = User.objects.get(pk=user_id) if user_id else None

        form = WizardOrganisationForm(request.POST, user=user)

        if form.is_valid():
            # Manually create the OrganisationalUnit
            org_unit = OrganisationalUnit.objects.create(
                name=form.cleaned_data['name'],
                description=form.cleaned_data.get('description', ''),
                lead=user
            )

            # Add the admin user as a member with manager role
            from chaotica_utils.enums import UnitRoles

            # Get or create manager role
            manager_role, _ = OrganisationalUnitRole.objects.get_or_create(
                pk=UnitRoles.MANAGER,
                defaults={'name': 'Manager', 'manage_role': True}
            )

            membership = OrganisationalUnitMember.objects.create(
                unit=org_unit,
                member=user
            )
            membership.roles.add(manager_role)

            # Store in session
            wizard_data['org_unit_id'] = org_unit.pk
            wizard_data['org_unit_name'] = org_unit.name
            request.session['wizard_data'] = wizard_data

            messages.success(request, f"Organisation unit '{org_unit.name}' created successfully!")
            return redirect(f'{request.path}?step=services')

        context = self.get_context(request, 'organisation')
        context['form'] = form
        return render(request, f"{self.template_base}organisation.html", context)

    @transaction.atomic
    def handle_services(self, request):
        """Handle services creation"""
        from jobtracker.models import Service
        form = WizardServiceForm(request.POST)

        if form.is_valid():
            services = form.cleaned_data['services']
            created_services = []

            for service_name in services:
                service, created = Service.objects.get_or_create(
                    name=service_name,
                    defaults={'description': f"Description for {service_name}"}
                )
                if created:
                    created_services.append(service_name)

            # Store in session
            wizard_data = request.session.get('wizard_data', {})
            wizard_data['services'] = created_services
            request.session['wizard_data'] = wizard_data

            messages.success(request, f"Created {len(created_services)} services!")
            return redirect(f'{request.path}?step=skills')

        context = self.get_context(request, 'services')
        context['form'] = form
        return render(request, f"{self.template_base}services.html", context)

    @transaction.atomic
    def handle_skills(self, request):
        """Handle skills creation"""
        from jobtracker.models import Skill, SkillCategory
        form = WizardSkillForm(request.POST)

        if form.is_valid():
            # Create categories
            categories = form.cleaned_data['categories']
            category_objects = {}

            for cat_name in categories:
                category, _ = SkillCategory.objects.get_or_create(
                    name=cat_name,
                    defaults={'description': f"Skills related to {cat_name}"}
                )
                category_objects[cat_name] = category

            # Create skills
            skills = form.cleaned_data['skills']
            created_skills = []

            for skill_data in skills:
                cat_name = skill_data['category']
                skill_name = skill_data['name']

                if cat_name in category_objects:
                    skill, created = Skill.objects.get_or_create(
                        name=skill_name,
                        category=category_objects[cat_name],
                        defaults={'description': f"Skill: {skill_name}"}
                    )
                    if created:
                        created_skills.append(skill_name)

            # Store in session
            wizard_data = request.session.get('wizard_data', {})
            wizard_data['categories'] = list(category_objects.keys())
            wizard_data['skills'] = created_skills
            request.session['wizard_data'] = wizard_data

            messages.success(request, f"Created {len(category_objects)} categories and {len(created_skills)} skills!")
            return redirect(f'{request.path}?step=clients')

        context = self.get_context(request, 'skills')
        context['form'] = form
        return render(request, f"{self.template_base}skills.html", context)

    @transaction.atomic
    def handle_clients(self, request):
        """Handle clients creation"""
        from jobtracker.models import Client
        form = WizardClientForm(request.POST)

        if form.is_valid():
            clients = form.cleaned_data['clients']
            created_clients = []

            wizard_data = request.session.get('wizard_data', {})
            user_id = wizard_data.get('admin_user_id')
            user = User.objects.get(pk=user_id) if user_id else None

            for client_name in clients:
                client, created = Client.objects.get_or_create(
                    name=client_name,
                    defaults={'short_name': client_name[:20]}
                )
                if created and user:
                    client.account_managers.add(user)
                    created_clients.append(client_name)

            # Store in session
            wizard_data['clients'] = created_clients
            request.session['wizard_data'] = wizard_data

            messages.success(request, f"Created {len(created_clients)} clients!")
            return redirect(f'{request.path}?step=complete')

        context = self.get_context(request, 'clients')
        context['form'] = form
        return render(request, f"{self.template_base}clients.html", context)

    def get_summary(self, wizard_data):
        """Get summary of created items"""
        return {
            'admin_user': wizard_data.get('admin_user_name', 'Not created'),
            'organisation': wizard_data.get('org_unit_name', 'Not created'),
            'services': wizard_data.get('services', []),
            'categories': wizard_data.get('categories', []),
            'skills': wizard_data.get('skills', []),
            'clients': wizard_data.get('clients', []),
        }

    def has_existing_data(self):
        """Check if any setup data already exists"""
        from jobtracker.models import OrganisationalUnit, Service, SkillCategory, Client

        return (
            User.objects.count() > 0 or
            OrganisationalUnit.objects.count() > 0 or
            Service.objects.count() > 0 or
            SkillCategory.objects.count() > 0 or
            Client.objects.count() > 0
        )

    def determine_current_step(self, request):
        """Determine which step the wizard should be on based on existing data"""
        from jobtracker.models import OrganisationalUnit, Service, SkillCategory, Client

        wizard_data = request.session.get('wizard_data', {})

        # Check what exists in the database
        has_user = User.objects.count() > 0
        has_org = OrganisationalUnit.objects.count() > 0
        has_service = Service.objects.count() > 0
        has_skills = SkillCategory.objects.count() > 0
        has_client = Client.objects.count() > 0

        # Determine the step based on what's missing
        if not has_user:
            return 'admin_user'
        elif not has_org:
            # User exists but no org, continue from organisation step
            # Try to recover the user info
            if 'admin_user_id' not in wizard_data and has_user:
                user = User.objects.filter(is_superuser=True).first()
                if user:
                    wizard_data['admin_user_id'] = user.pk
                    wizard_data['admin_user_name'] = f"{user.first_name} {user.last_name}"
                    request.session['wizard_data'] = wizard_data
            return 'organisation'
        elif not has_service:
            # Recover org info if needed
            if 'org_unit_id' not in wizard_data and has_org:
                org = OrganisationalUnit.objects.first()
                if org:
                    wizard_data['org_unit_id'] = org.pk
                    wizard_data['org_unit_name'] = org.name
                    request.session['wizard_data'] = wizard_data
            return 'services'
        elif not has_skills:
            return 'skills'
        elif not has_client:
            return 'clients'
        else:
            # Everything exists, show completion
            return 'complete'