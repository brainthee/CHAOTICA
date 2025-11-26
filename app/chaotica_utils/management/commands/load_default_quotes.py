import json
import os
from django.conf import settings as django_settings
from datetime import datetime, timedelta, date
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from chaotica_utils.models import Quote


class Command(BaseCommand):
    help = 'Loads default quotes for CHAOTICA system'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Loading default quotes...'))

        lines = json.load(
            open(
                os.path.join(
                    django_settings.BASE_DIR, "chaotica_utils/templates/quotes.json"
                )
            )
        )

        for line in lines:
            q,_created = Quote.objects.get_or_create(
                author=line["author"].strip(),
                content=line["quote"].strip()
            )
            if _created:
                self.stdout.write(self.style.SUCCESS("Creating {} - {}".format(line["author"], line["quote"])))
            else:
                self.stdout.write(self.style.SUCCESS("Skipped {} - {}".format(line["author"], line["quote"])))

        self.stdout.write(self.style.SUCCESS('Default quotes loaded successfully!'))
