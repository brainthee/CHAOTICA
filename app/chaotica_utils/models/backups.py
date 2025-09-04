# models.py
from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()

class ManualBackupJob(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('complete', 'Complete'),
        ('failed', 'Failed'),
    ]
    
    TYPE_CHOICES = [
        ('media', 'Media Backup'),
        ('db', 'Database Backup'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    backup_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='db')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    file_path = models.CharField(max_length=500, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        
    def get_filename(self):
        """Get appropriate filename based on backup type"""
        if self.backup_type == 'media':
            return 'media_backup.tar.gz'
        else:
            return 'db_backup.gz'
    
    def get_content_type(self):
        """Get appropriate content type"""
        return 'application/gzip'