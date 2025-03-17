from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import PetPreference
from .forms import PetPreferenceForm  # Create a ModelForm for PetPreference
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import PetPreference
from .forms import PetPreferenceForm


@login_required
def pet_settings(request):
    """View for managing virtual pet settings"""
    # Get or create preferences for the user
    preferences, created = PetPreference.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = PetPreferenceForm(request.POST, instance=preferences)
        if form.is_valid():
            form.save()
            return redirect('dashboard')  # Redirect to main app page
    else:
        form = PetPreferenceForm(instance=preferences)
    
    return render(request, 'virtualpet/settings.html', {
        'form': form,
        'pet': preferences
    })

@login_required
@require_POST
def toggle_pet(request):
    """Simple view to toggle the pet on/off"""
    preferences, created = PetPreference.objects.get_or_create(user=request.user)
    preferences.enabled = not preferences.enabled
    preferences.save()
    
    return JsonResponse({
        'enabled': preferences.enabled
    })

@login_required
def team_pets(request):
    """View for displaying all team pets"""
    from django.db.models import Max, Avg
    
    # Get basic stats on team pets
    pet_count = PetPreference.objects.filter(enabled=True).count()
    
    # Get user with highest happiness
    happiest_pet = PetPreference.objects.filter(enabled=True).order_by('-current_happiness').first()
    
    # Get user with most pentest completions
    from .models import PetStatistics
    top_pentester = PetStatistics.objects.all().order_by('-phase_completions').first()
    
    # Average happiness across team
    avg_happiness = PetPreference.objects.filter(enabled=True).aggregate(Avg('current_happiness'))
    
    return render(request, 'virtualpet/team.html', {
        'pet_count': pet_count,
        'happiest_pet': happiest_pet,
        'top_pentester': top_pentester,
        'avg_happiness': avg_happiness.get('current_happiness__avg', 0) if avg_happiness else 0
    })

def get_pet_config_js(request):
    """Generate JavaScript config for the pet"""
    if not request.user.is_authenticated:
        return JsonResponse({'enabled': False})
    
    try:
        pet = PetPreference.objects.get(user=request.user)
        config = pet.to_dict()
    except PetPreference.DoesNotExist:
        config = {
            'name': f"{request.user.username}'s Pet",
            'position': 'bottom-right',
            'size': 'medium',
            'enabled': True,
            'syncWithServer': True
        }
    
    # Return as JavaScript
    js_content = f"window.petConfig = {JsonResponse(config).content.decode('utf-8')};"
    
    from django.http import HttpResponse
    return HttpResponse(js_content, content_type="application/javascript")