from django.contrib import admin
from .models import RMSyncRecord, RMAssignable, RMAssignableSlot

# Register your models here.

@admin.register(RMAssignableSlot)
class SlotAdmin(admin.ModelAdmin):
    readonly_fields=('slot',)
    list_display=[ 
        "pk",
        "rm_id",
        "slot", 
        "last_sync_result",
        "last_synced",]

@admin.register(RMAssignable)
class AssignAdmin(admin.ModelAdmin):
    readonly_fields=('phase', 'project',)
    list_display=[ 
        "pk",
        "rm_id",
        "project", 
        "phase",
        "last_sync_result",
        "last_synced",]

@admin.register(RMSyncRecord)
class SyncAdmin(admin.ModelAdmin):
    readonly_fields=('user',)
    list_display=[
        "pk",
        "user", 
        "rm_id",
        "sync_enabled",
        "sync_authoritative",
        "last_sync_result",
        "last_synced",
    ]