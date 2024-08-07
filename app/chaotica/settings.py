from pathlib import Path
import os
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from dotenv import load_dotenv
import datetime

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = int(os.environ.get("DEBUG", default=0))
MAINTENANCE_MODE = int(os.environ.get("MAINTENANCE_MODE", default=0))

DJANGO_ENV = os.environ.get("DJANGO_ENV", default="Dev")
DJANGO_VERSION = os.environ.get("DJANGO_VERSION", default="bleeding-edge")

SENTRY_DSN = os.environ.get("SENTRY_DSN", default=None)

if SENTRY_DSN is not None:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        send_default_pii=True,
        environment=DJANGO_ENV,
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )


SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    default="this-aint-secure-honest-f7r-nrel3@s^c5gl!%l8-i)eeea++xm_(qpl+!=$1$_40nh=ym",
)

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", default="* web").split(" ")
USE_X_FORWARDED_HOST = bool(os.environ.get("USE_X_FORWARDED_HOST", default=True))
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_COOKIE_SECURE = bool(os.environ.get("CSRF_COOKIE_SECURE", default=False))
SESSION_COOKIE_SECURE = bool(os.environ.get("SESSION_COOKIE_SECURE", default=False))
SESSION_EXPIRE_AT_BROWSER_CLOSE = bool(
    os.environ.get("SESSION_EXPIRE_AT_BROWSER_CLOSE", default=True)
)
SESSION_COOKIE_AGE = int(os.environ.get("SESSION_COOKIE_AGE", default=60 * 60 * 12))

AUTH_ADFS = {
    "AUDIENCE": os.environ.get("ADFS_CLIENT_ID", default="xx"),
    "CLIENT_ID": os.environ.get("ADFS_CLIENT_ID", default="xx"),
    "CLIENT_SECRET": os.environ.get("ADFS_CLIENT_SECRET", default="xx"),
    "CLAIM_MAPPING": {"first_name": "given_name", "last_name": "family_name"},
    "USERNAME_CLAIM": {"email": "upn"},
    "GROUPS_CLAIM": None,
    "MIRROR_GROUPS": False,
    "USERNAME_CLAIM": "upn",
    "TENANT_ID": os.environ.get("ADFS_TENANT_ID", default="xx"),
    "RELYING_PARTY_ID": os.environ.get("ADFS_CLIENT_ID", default="xx"),
    "LOGIN_EXEMPT_URLS": [
        "quote",
        "password_reset",
        "reset",
    ],
}

EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", default="localhost")
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", default="user")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", default="Hunter2")
EMAIL_PORT = os.environ.get("EMAIL_PORT", default=25)
EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", default=False)
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", default="CHAOTICA <notifications@chaotica.app>"
)

# Development on CHAOTICA started on this day (in a private repo)
# CHAOTICA_BIRTHDAY = datetime.date(2023, 8, 4)
CHAOTICA_BIRTHDAY = datetime.date(2023, 6, 21)

GLOBAL_GROUP_PREFIX = "Global: "

DATA_UPLOAD_MAX_NUMBER_FILES = 5000

DEFAULT_HOURS_IN_DAY = os.environ.get("DEFAULT_HOURS_IN_DAY", default=7.5)

CONSTANCE_CONFIG = {
    # Feature Flags
    "ADFS_ENABLED": (
        False,
        "Should we allow ADFS login? Ensure there is a valid configuration!",
    ),
    "REGISTRATION_ENABLED": (True, "Should we allow self-registration?"),
    "LOCAL_LOGIN_ENABLED": (True, "Should we allow logging in via local user?"),
    # Invite
    "INVITE_ENABLED": (True, "Should we allow inviting users?"),
    "USER_INVITE_EXPIRY": (7, "How long until invites expire"),
    # Skills refresher
    "SKILLS_REVIEW_DAYS": (
        31,
        "How many days we should prompt users to review their skills",
    ),
    "PROFILE_REVIEW_DAYS": (
        182,
        "How many days we should prompt users to review their profile",
    ),
    # Phase ID settings
    "JOB_ID_START": (2500, "Where to start Job IDs"),
    # 'PHASE_ID_START': (1, 'Where Phase IDs start'),
    # Notification Settings
    "TQA_LATE_HOURS": (
        24,
        "How many hours before sending another late to TQA notficiation",
    ),
    "PQA_LATE_HOURS": (
        24,
        "How many hours before sending another late to PQA notficiation",
    ),
    "DELIVERY_LATE_HOURS": (
        24,
        "How many hours before sending another late to Delivery notficiation",
    ),
    # Work settings
    "DEFAULT_HOURS_IN_DAY": (7.5, "Default hours in a work day"),
    "LEAVE_DAYS_NOTICE": (14, "How many days notice for Annual Leave submissions?"),
    # Theme/Look settings
    "SNOW_ENABLED": (False, "Should it snow?"),
    "KONAMI_ENABLED": (True, "Should the Konami easter-egg be enabled?"),
    # Site Notice
    "SITE_NOTICE_ENABLED": (False, "Show a site wide notice"),
    "SITE_NOTICE_MSG": ("", "Message to display across the site"),
    "SITE_NOTICE_COLOUR": (
        "primary",
        "Select the alert colour of the site notice",
        "notice_colour",
    ),
    # Schedule Colours
    "SCHEDULE_COLOR_AVAILABLE": (
        "#E224A3",
        "Colour to show available in the schedule",
        "colour_picker",
    ),
    "SCHEDULE_COLOR_UNAVAILABLE": (
        "#E224A3",
        "Colour to show available in the schedule",
        "colour_picker",
    ),
    "SCHEDULE_COLOR_INTERNAL": (
        "#E224A3",
        "Colour to show available in the schedule",
        "colour_picker",
    ),
    "SCHEDULE_COLOR_PHASE_CONFIRMED": (
        "#E224A3",
        "Colour to show available in the schedule",
        "colour_picker",
    ),
    "SCHEDULE_COLOR_PHASE_CONFIRMED_AWAY": (
        "#E224A3",
        "Colour to show available in the schedule",
        "colour_picker",
    ),
    "SCHEDULE_COLOR_PHASE": (
        "#E224A3",
        "Colour to show available in the schedule",
        "colour_picker",
    ),
    "SCHEDULE_COLOR_PHASE_AWAY": (
        "#E224A3",
        "Colour to show available in the schedule",
        "colour_picker",
    ),
}

CONSTANCE_BACKEND = "constance.backends.database.DatabaseBackend"
CONSTANCE_IGNORE_ADMIN_VERSION_CHECK = True
CONSTANCE_ADDITIONAL_FIELDS = {
    "image_field": ["django.forms.ImageField", {}],
    "colour_picker": [
        "django.forms.CharField",
        {
            "widget": "colorfield.widgets.ColorWidget",
        },
    ],
    "notice_colour": [
        "django.forms.fields.ChoiceField",
        {
            "widget": "django.forms.Select",
            "choices": (
                ("primary", "Primary"),
                ("secondary", "Secondary"),
                ("info", "Info"),
                ("success", "Success"),
                ("danger", "Danger"),
                ("warning", "Warning"),
            ),
        },
    ],
}


AUTHENTICATION_BACKENDS = (
    "django.contrib.auth.backends.ModelBackend",
    "guardian.backends.ObjectPermissionBackend",
    "django_auth_adfs.backend.AdfsAuthCodeBackend",
)

GUARDIAN_RAISE_403 = True
GUARDIAN_TEMPLATE_403 = "403.html"

SITE_DOMAIN = os.environ.get("SITE_DOMAIN", default="127.0.0.1:8000")
SITE_PROTO = os.environ.get("SITE_PROTO", default="http")
AUTH_USER_MODEL = "chaotica_utils.User"
LOGIN_URL = "/auth/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# Twilio
TWILIO_ACC = os.environ.get("TWILIO_ACC", default="Hunter2")
TWILIO_TOKEN = os.environ.get("TWILIO_TOKEN", default="Hunter2")
TWILIO_SERVICESID = os.environ.get("TWILIO_SERVICESID", default="Hunter2")

# Application definition
DEFAULT_APPS = [
    # Have to add these here as they must be loaded in before everything else
    "dal",
    "dal_select2",
    "django.contrib.admin",
    "django.contrib.admindocs",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]
THIRD_PARTY_APPS = [
    "colorfield",
    "constance",
    "django_auth_adfs",
    "menu",
    "widget_tweaks",
    "guardian",
    "crispy_forms",
    "crispy_bootstrap5",
    "tinymce",
    "django_bleach",
    "django_fsm",
    "phonenumber_field",
    "simple_history",
    "rest_framework",
    "django_filters",
    "impersonate",
    "import_export",
    "explorer",
    "bootstrap_datepicker_plus",
    "location_field.apps.DefaultConfig",
    "storages",
    "django_cron",
    'dbbackup',  # django-dbbackup
]
LOCAL_APPS = [
    "chaotica_utils",
    "jobtracker",
    "dashboard",
]

INSTALLED_APPS = DEFAULT_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# Which HTML tags are allowed
BLEACH_ALLOWED_TAGS = [
    "p",
    "s",
    "span",
    "b",
    "i",
    "u",
    "em",
    "strong",
    "a",
    "ul",
    "li",
    "ol",
]
# Which HTML attributes are allowed
BLEACH_ALLOWED_ATTRIBUTES = ["href", "title", "style"]
# Which CSS properties are allowed in 'style' attributes (assuming style is
# an allowed attribute)
BLEACH_ALLOWED_STYLES = [
    "font-family",
    "text-align",
    "font-weight",
    "text-decoration",
    "font-variant",
]
# Which protocols (and pseudo-protocols) are allowed in 'src' attributes
# (assuming src is an allowed attribute)
BLEACH_ALLOWED_PROTOCOLS = ["http", "https", "data"]

DJANGO_CRON_DELETE_LOGS_OLDER_THAN = 14
CRON_CLASSES = [
    "chaotica_utils.tasks.task_update_holidays",
    "chaotica_utils.tasks.task_send_email_notifications",
    "chaotica_utils.tasks.task_sync_global_permissions",
    "chaotica_utils.tasks.task_sync_role_permissions_to_default",
    "chaotica_utils.tasks.task_sync_role_permissions",

    "chaotica_utils.tasks.task_backup_site",

    "jobtracker.tasks.task_progress_workflows",
    "jobtracker.tasks.task_fire_job_notifications",
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
}

MIDDLEWARE = [
    "chaotica_utils.middleware.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "impersonate.middleware.ImpersonateMiddleware",
    "chaotica_utils.middleware.NewInstallMiddleware",
    "chaotica_utils.middleware.MaintenanceModeMiddleware",
]

ROOT_URLCONF = "chaotica.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "constance.context_processors.config",
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.template.context_processors.static",
                "django.template.context_processors.media",
                "chaotica_utils.context_processors.defaults",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "chaotica.wsgi.application"


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": os.environ.get("SQL_ENGINE", "django.db.backends.sqlite3"),
        "NAME": os.environ.get("RDS_DB_NAME", os.path.join(BASE_DIR, "db.sqlite3")),
        "USER": os.environ.get("RDS_USERNAME", "root"),
        "PASSWORD": os.environ.get("RDS_PASSWORD", "chaoticadb1"),
        "HOST": os.environ.get("RDS_HOSTNAME", "127.0.0.1"),
        "PORT": os.environ.get("RDS_PORT", "13306"),
        "DEFAULT-CHARACTER-SET": "utf8",
        # 'OPTIONS': {
        #     "init_command": "SET GLOBAL max_connections = 100000",
        # }
    }
}


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("TZ", default="Europe/London")
USE_I18N = True
USE_L10N = True
USE_TZ = True

# Backups
DBBACKUP_CLEANUP_KEEP = os.environ.get("DBBACKUP_CLEANUP_KEEP", default=60)
DBBACKUP_CLEANUP_KEEP_MEDIA = os.environ.get("DBBACKUP_CLEANUP_KEEP_MEDIA", default=60)

DBBACKUP_ENABLED = os.environ.get("DBBACKUP_ENABLED", default=False)
if DBBACKUP_ENABLED == "1" or DBBACKUP_ENABLED:
    DBBACKUP_STORAGE = os.environ.get("DBBACKUP_STORAGE", default='django.core.files.storage.FileSystemStorage')
    if "FileSystemStorage" in DBBACKUP_STORAGE:
        DBBACKUP_STORAGE_OPTIONS = {
            'location': os.environ.get("DBBACKUP_FS_LOCATION", default='')
        }
    if "S3Boto3Storage" in DBBACKUP_STORAGE:
        DBBACKUP_STORAGE_OPTIONS = {
            'access_key': os.environ.get("DBBACKUP_S3_AKEY", default=''),
            'secret_key': os.environ.get("DBBACKUP_S3_SKEY", default=''),
            'bucket_name': os.environ.get("DBBACKUP_S3_BUCKET_NAME", default=''),
            'default_acl': os.environ.get("DBBACKUP_S3_DEFAULT_ACL", default=''),
        }

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

USE_S3 = os.environ.get("USE_S3", default=False)

if USE_S3 == "1" or USE_S3:
    # aws settings
    AWS_ACCESS_KEY_ID = os.getenv("AWS_STORAGE_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_STORAGE_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME")
    AWS_DEFAULT_ACL = "public-read"
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}
    if os.getenv("AWS_STORAGE_CLOUDFRONT_DOMAIN", None):
        # Use CloudFront
        AWS_S3_CUSTOM_DOMAIN = os.getenv("AWS_STORAGE_CLOUDFRONT_DOMAIN", None)
        DEFAULT_FILE_STORAGE = 'chaotica.storage.MediaStorage'
        STATICFILES_STORAGE = 'chaotica.storage.StaticStorage'
        
        AWS_CLOUDFRONT_KEY = os.environ.get('AWS_STORAGE_CLOUDFRONT_KEY', None).encode('ascii') 
        AWS_CLOUDFRONT_KEY_ID = os.environ.get('AWS_STORAGE_CLOUDFRONT_KEY_ID', None)
    else:
        # Use S3 directly
        AWS_S3_CUSTOM_DOMAIN = f"{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com"
        DEFAULT_FILE_STORAGE = "storages.backends.s3.S3Storage"
        STATICFILES_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"

    MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/media/"
    STATIC_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/static/"
else:
    MEDIA_URL = "/media/"
    MEDIA_ROOT = os.path.join(BASE_DIR, "mediafiles")
    STATIC_URL = "/static/"
    STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

STATICFILES_DIRS = (os.path.join(BASE_DIR, "static"),)

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Explorer SQL
# Should setup readonly DB roles ideally for this...
# EXPLORER_CONNECTIONS = { 'Default': 'readonly' }
# EXPLORER_DEFAULT_CONNECTION = 'readonly'
EXPLORER_CONNECTIONS = {"Default": "default"}
EXPLORER_DEFAULT_CONNECTION = "default"
EXPLORER_SQL_BLACKLIST = (
    # DML
    "COMMIT",
    "DELETE",
    "INSERT",
    "MERGE",
    "REPLACE",
    "ROLLBACK",
    "SET",
    "START",
    "UPDATE",
    "UPSERT",
    # DDL
    "ALTER",
    "CREATE",
    "DROP",
    "RENAME",
    "TRUNCATE",
    # DCL
    "GRANT",
    "REVOKE",
)
EXPLORER_PERMISSION_VIEW = lambda r: r.user.is_staff
EXPLORER_PERMISSION_CHANGE = lambda r: r.user.is_staff
EXPLORER_DATA_EXPORTERS = [
    ("csv", "explorer.exporters.CSVExporter"),
    ("excel", "explorer.exporters.ExcelExporter"),
    ("json", "explorer.exporters.JSONExporter"),
]
