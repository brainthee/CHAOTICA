from django.conf import settings
from chaotica_utils.utils.utilisation import UTILISATION_FORMULA_DESCRIPTION


def defaults(_):
    return {
        "SENTRY_FRONTEND_DSN": settings.SENTRY_FRONTEND_DSN,
        # Single source of truth for the utilisation formula explanation, so the
        # UI tooltip always matches the code (see chaotica_utils.utils.utilisation).
        "UTILISATION_FORMULA_DESCRIPTION": UTILISATION_FORMULA_DESCRIPTION,
    }
