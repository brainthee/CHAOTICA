# virtualpet/admin.py

from django.contrib import admin
from .models import PetPreference, PetStatistics, PetAchievement, TeamPetEvent

class PetStatisticsInline(admin.StackedInline):
    model = PetStatistics
    can_delete = False
    verbose_name_plural = 'Pet Statistics'

class PetAchievementInline(admin.TabularInline):
    model = PetAchievement
    extra = 0
    verbose_name_plural = 'Pet Achievements'

@admin.register(PetPreference)
class PetPreferenceAdmin(admin.ModelAdmin):
    list_display = ('pet_name', 'user', 'enabled', 'current_happiness', 'last_interaction')
    list_filter = ('enabled', 'pet_size', 'pet_position')
    search_fields = ('pet_name', 'user__username')
    inlines = [PetStatisticsInline, PetAchievementInline]
    readonly_fields = ('created_date', 'modified_date')
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'pet_name', 'enabled')
        }),
        ('Appearance', {
            'fields': ('pet_position', 'pet_size')
        }),
        ('State', {
            'fields': ('current_happiness', 'current_energy', 'last_state', 'last_fed', 'last_interaction')
        }),
        ('Metadata', {
            'fields': ('created_date', 'modified_date'),
            'classes': ('collapse',)
        }),
    )

@admin.register(PetStatistics)
class PetStatisticsAdmin(admin.ModelAdmin):
    list_display = ('pet_preference', 'phase_completions', 'total_feeds', 'average_happiness')
    list_filter = ('phase_completions',)
    search_fields = ('pet_preference__pet_name', 'pet_preference__user__username')
    readonly_fields = ('created_date', 'modified_date')

@admin.register(PetAchievement)
class PetAchievementAdmin(admin.ModelAdmin):
    list_display = ('achievement_name', 'pet_preference', 'unlocked_date')
    list_filter = ('achievement_id', 'unlocked_date')
    search_fields = ('achievement_name', 'pet_preference__pet_name')

@admin.register(TeamPetEvent)
class TeamPetEventAdmin(admin.ModelAdmin):
    list_display = ('title', 'start_date', 'end_date', 'is_active', 'is_current')
    list_filter = ('is_active', 'start_date', 'end_date')
    search_fields = ('title', 'description')
    
    def is_current(self, obj):
        return obj.is_current
    is_current.boolean = True