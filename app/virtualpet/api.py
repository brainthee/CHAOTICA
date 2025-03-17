# virtualpet/api.py

from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required
import json
from datetime import datetime, timedelta
from .models import PetPreference, PetStatistics

@require_POST
@login_required
def sync_pet_data(request):
    """
    Synchronize pet data between client and server
    """
    try:
        data = json.loads(request.body)
        
        # Get or create pet preference
        preference, _ = PetPreference.objects.get_or_create(user=request.user)
        
        # Update basic preferences if provided
        if 'pet_name' in data:
            preference.pet_name = data['pet_name']
            
        # Track happiness and energy
        preference.current_happiness = data.get('happiness', preference.current_happiness)
        preference.current_energy = data.get('energy', preference.current_energy)
        preference.last_state = data.get('state', preference.last_state)
        
        # Parse dates if provided
        if 'last_fed' in data:
            preference.last_fed = datetime.fromisoformat(data['last_fed'].replace('Z', '+00:00'))
            
        if 'last_interaction' in data:
            preference.last_interaction = datetime.fromisoformat(data['last_interaction'].replace('Z', '+00:00'))
            
        preference.save()
        
        # Update statistics if provided
        if 'statistics' in data:
            stats, _ = PetStatistics.objects.get_or_create(pet_preference=preference)
            
            stats_data = data['statistics']
            if 'total_feeds' in stats_data:
                stats.total_feeds = stats_data['total_feeds']
                
            if 'total_plays' in stats_data:
                stats.total_plays = stats_data['total_plays']
                
            if 'total_pets' in stats_data:
                stats.total_pets = stats_data['total_pets']
                
            if 'total_sleeps' in stats_data:
                stats.total_sleeps = stats_data['total_sleeps']
                
            if 'phase_completions' in stats_data:
                stats.phase_completions = stats_data['phase_completions']
                
            stats.save()
        
        return JsonResponse({
            'status': 'success',
            'message': 'Pet data synchronized successfully'
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)
        
@require_GET
@login_required
def get_team_pets(request):
    """
    Get data about all team members' pets for the team ranking
    """
    # Get all active pets (interacted with in the last 30 days)
    active_date = datetime.now() - timedelta(days=30)
    active_pets = PetPreference.objects.filter(
        last_interaction__gte=active_date,
        enabled=True
    ).select_related('user', 'petstatistics')
    
    pets_data = []
    for pet in active_pets:
        # Calculate pet age in days
        created_date = pet.created_date or pet.user.date_joined
        age_days = (datetime.now().date() - created_date.date()).days
        
        # Get statistics if available
        phase_completions = 0
        if hasattr(pet, 'petstatistics'):
            phase_completions = pet.petstatistics.phase_completions
        
        pets_data.append({
            'user_name': pet.user.get_full_name() or pet.user.username,
            'pet_name': pet.pet_name,
            'happiness': pet.current_happiness,
            'energy': pet.current_energy,
            'phase_completions': phase_completions,
            'age_days': age_days,
            'last_interaction': pet.last_interaction.isoformat() if pet.last_interaction else None
        })
    
    return JsonResponse({
        'status': 'success',
        'pets': pets_data
    })
    
@require_POST
@login_required
def toggle_pet(request):
    """
    Toggle the pet on/off
    """
    preference, created = PetPreference.objects.get_or_create(user=request.user)
    preference.enabled = not preference.enabled
    preference.save()
    
    return JsonResponse({
        'status': 'success',
        'enabled': preference.enabled
    })
    
@require_POST
@login_required
def record_pentest_completion(request):
    """
    Record a pentest completion to update statistics
    """
    try:
        preference, _ = PetPreference.objects.get_or_create(user=request.user)
        stats, _ = PetStatistics.objects.get_or_create(pet_preference=preference)
        
        # Increment pentest completions
        stats.phase_completions += 1
        stats.save()
        
        return JsonResponse({
            'status': 'success',
            'phase_completions': stats.phase_completions
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)