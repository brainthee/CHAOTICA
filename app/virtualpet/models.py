# virtualpet/models.py

from django.db import models
from django.conf import settings
from django.utils import timezone

class PetPreference(models.Model):
    """
    Stores user preferences for their virtual pet
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    pet_name = models.CharField(max_length=50, default="Bitsy")
    pet_position = models.CharField(
        max_length=20, 
        choices=[
            ('bottom-right', 'Bottom Right'),
            ('bottom-left', 'Bottom Left'),
            ('top-right', 'Top Right'),
            ('top-left', 'Top Left')
        ],
        default='bottom-right'
    )
    pet_size = models.CharField(
        max_length=10,
        choices=[
            ('small', 'Small'),
            ('medium', 'Medium'),
            ('large', 'Large')
        ],
        default='medium'
    )
    enabled = models.BooleanField(default=True)
    created_date = models.DateTimeField(auto_now_add=True)
    modified_date = models.DateTimeField(auto_now=True)
    
    # Pet state data
    current_happiness = models.FloatField(default=80)
    current_energy = models.FloatField(default=100)
    last_state = models.CharField(max_length=20, default='idle')
    last_fed = models.DateTimeField(null=True, blank=True)
    last_interaction = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.user.username}'s pet: {self.pet_name}"
    
    def to_dict(self):
        """
        Convert to dictionary for passing to JavaScript
        """
        return {
            'name': self.pet_name,
            'position': self.pet_position,
            'size': self.pet_size,
            'enabled': self.enabled,
            'happiness': self.current_happiness,
            'energy': self.current_energy,
            'state': self.last_state,
            'syncWithServer': True
        }
    
    def save(self, *args, **kwargs):
        # Update the last_interaction time if not set
        if not self.last_interaction:
            self.last_interaction = timezone.now()
        super().save(*args, **kwargs)

class PetStatistics(models.Model):
    """
    Stores statistics about the pet's usage and interaction
    """
    pet_preference = models.OneToOneField(PetPreference, on_delete=models.CASCADE)
    total_feeds = models.IntegerField(default=0)
    total_plays = models.IntegerField(default=0)
    total_pets = models.IntegerField(default=0)
    total_sleeps = models.IntegerField(default=0)
    longest_happiness_streak = models.IntegerField(default=0)
    current_happiness_streak = models.IntegerField(default=0)
    highest_happiness = models.FloatField(default=80)
    lowest_happiness = models.FloatField(default=80)
    average_happiness = models.FloatField(default=80)
    phase_completions = models.IntegerField(default=0)
    created_date = models.DateTimeField(auto_now_add=True)
    modified_date = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Stats for {self.pet_preference.pet_name}"
    
    class Meta:
        verbose_name_plural = "Pet Statistics"

class PetAchievement(models.Model):
    """
    Tracks achievements unlocked by the pet
    """
    pet_preference = models.ForeignKey(PetPreference, on_delete=models.CASCADE, related_name='achievements')
    achievement_id = models.CharField(max_length=50)
    achievement_name = models.CharField(max_length=100)
    unlocked_date = models.DateTimeField(default=timezone.now)
    
    class Meta:
        unique_together = ('pet_preference', 'achievement_id')
    
    def __str__(self):
        return f"{self.achievement_name} ({self.pet_preference.pet_name})"

class TeamPetEvent(models.Model):
    """
    Tracks team-wide pet events like competitions or challenges
    """
    title = models.CharField(max_length=100)
    description = models.TextField()
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.title
    
    @property
    def is_current(self):
        """
        Check if this event is currently running
        """
        now = timezone.now()
        return self.start_date <= now <= self.end_date and self.is_active