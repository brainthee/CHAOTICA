from django.conf import settings
from django.db.models.signals import post_save
from .models import User
from pprint import pprint
from django.core.exceptions import ObjectDoesNotExist
