from django.db.models import Manager

class SystemNoteManager(Manager):
    def get_query_set(self):
        return super(SystemNoteManager, self).get_query_set().filter(is_system_note=True)