from pathlib import Path
import os
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from dotenv import load_dotenv
import datetime
import base64
from csp.constants import SELF, UNSAFE_INLINE, UNSAFE_EVAL, NONCE


load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = int(os.environ.get("DEBUG", default=0))
MAINTENANCE_MODE = int(os.environ.get("MAINTENANCE_MODE", default=0))

DJANGO_ENV = os.environ.get("DJANGO_ENV", default="Dev")
DJANGO_VERSION = os.environ.get("DJANGO_VERSION", default="bleeding-edge")

SENTRY_BACKEND_DSN = os.environ.get("SENTRY_BACKEND_DSN", default=None)
SENTRY_FRONTEND_DSN = os.environ.get("SENTRY_FRONTEND_DSN", default=None)

if SENTRY_BACKEND_DSN is not None:
    sentry_sdk.init(
        dsn=SENTRY_BACKEND_DSN,
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

SITE_DOMAIN = os.environ.get("SITE_DOMAIN", default="127.0.0.1:8000")
SITE_PROTO = os.environ.get("SITE_PROTO", default="http")

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", default="* web").split(" ")
USE_X_FORWARDED_HOST = bool(os.environ.get("USE_X_FORWARDED_HOST", default=True))
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# These 4 options should not be set in dev envs
if DJANGO_ENV != "Dev":
    CSRF_COOKIE_SECURE = bool(os.environ.get("CSRF_COOKIE_SECURE", default=True))
    CSRF_COOKIE_SAMESITE = os.environ.get("CSRF_COOKIE_SAMESITE", default="None")
    SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", default="None")
    SESSION_COOKIE_SECURE = bool(os.environ.get("SESSION_COOKIE_SECURE", default=True))
SESSION_EXPIRE_AT_BROWSER_CLOSE = bool(
    os.environ.get("SESSION_EXPIRE_AT_BROWSER_CLOSE", default=True)
)
SESSION_COOKIE_AGE = int(os.environ.get("SESSION_COOKIE_AGE", default=60 * 60 * 12))

MAXMIND_LICENSE_KEY = os.environ.get("MAXMIND_LICENSE_KEY", default="")
GEOIP_PATH = os.environ.get("GEOIP_PATH", default="/tmp/geoip")

AUTH_ADFS = {
    "AUDIENCE": os.environ.get("ADFS_CLIENT_ID", default="xx"),
    "CLIENT_ID": os.environ.get("ADFS_CLIENT_ID", default="xx"),
    "CLIENT_SECRET": os.environ.get("ADFS_CLIENT_SECRET", default="xx"),
    "CLAIM_MAPPING": {"first_name": "given_name", "last_name": "family_name"},
    "GROUPS_CLAIM": None,
    "MIRROR_GROUPS": False,
    # "USERNAME_CLAIM": {"email": "upn"},
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

DATA_UPLOAD_MAX_NUMBER_FILES = 10000
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000

DEFAULT_HOURS_IN_DAY = os.environ.get("DEFAULT_HOURS_IN_DAY", default=7.5)

CONSTANCE_CONFIG = {
    # Feature Flags
    "EMAIL_ENABLED": (
        False,
        "Despite email configuration - should we send emails?",
    ),
    "ADFS_ENABLED": (
        False,
        "Should we allow ADFS login? Ensure there is a valid configuration!",
    ),
    "ADFS_AUTO_LOGIN": (
        False,
        "Should we auto redirect to ADFS login? Ensure there is a valid configuration!",
    ),
    "REGISTRATION_ENABLED": (True, "Should we allow self-registration?"),
    "LOCAL_LOGIN_ENABLED": (True, "Should we allow logging in via local user?"),
    # Support
    "SUPPORT_DOC_URL": ("https://docs.chaotica.app/en/latest/", "URL to Documentation"),
    "SUPPORT_MAILBOX": (
        "https://github.com/brainthee/CHAOTICA/issues",
        "URL to request support",
    ),
    "SUPPORT_ISSUES": ("https://github.com/brainthee/CHAOTICA/issues", "URL to issues"),
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
    "PROJECT_ID_START": (9000, "Where to start Project IDs"),
    # Notification Settings
    "PRECHECK_LATE_HOURS": (
        24,
        "How many hours before sending another late Prechecks notficiation",
    ),
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
    # Default days to TQA/PQA/Delivery
    "DAYS_TO_TQA": (
        0,
        "How many days after the last testing/reporting slot should a job be due to TQA.",
    ),
    "DAYS_TO_PQA": (
        5,
        "How many days after the last testing/reporting slot should a job be due to PQA.",
    ),
    "DAYS_TO_DELIVERY": (
        7,
        "How many days after the last testing/reporting slot should a job be due to Delivery.",
    ),
    # Work settings
    "DEFAULT_HOURS_IN_DAY": (7.5, "Default hours in a work day"),
    "DEFAULT_WORKING_DAYS": (
        "[1, 2, 3, 4, 5]",
        "An int array with the numbers equaling the day of the week. Sunday == 0, Monday == 1 etc",
    ),
    "LEAVE_DAYS_NOTICE": (14, "How many days notice for Annual Leave submissions?"),
    "LEAVE_ENFORCE_LIMIT": (False, "Should leave be prevented if over balance?"),
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
        "#8BC34A",
        "Colour to show available in the schedule",
        "colour_picker",
    ),
    "SCHEDULE_COLOR_UNAVAILABLE": (
        "#F44336",
        "Colour to show available in the schedule",
        "colour_picker",
    ),
    "SCHEDULE_COLOR_INTERNAL": (
        "#FFC107",
        "Colour to show available in the schedule",
        "colour_picker",
    ),
    "SCHEDULE_COLOR_PROJECT": (
        "#9C27B0",
        "Colour to show available in the schedule",
        "colour_picker",
    ),
    "SCHEDULE_COLOR_PHASE": (
        "#A3E1FF",
        "Colour to show available in the schedule",
        "colour_picker",
    ),
    "SCHEDULE_COLOR_PHASE_CONFIRMED": (
        "#239DFF",
        "Colour to show available in the schedule",
        "colour_picker",
    ),
    "SCHEDULE_COLOR_PHASE_AWAY": (
        "#FFBCA9",
        "Colour to show available in the schedule",
        "colour_picker",
    ),
    "SCHEDULE_COLOR_PHASE_CONFIRMED_AWAY": (
        "#FF5722",
        "Colour to show available in the schedule",
        "colour_picker",
    ),
    "SCHEDULE_COLOR_COMMENT": (
        "#cbd0dd",
        "Colour to show comments",
        "colour_picker",
    ),
    # Notification boxes
    "NOTIFICATION_POOL_SCOPING_EMAIL_RCPTS": (
        "",
        "Additional email recipients for Scoping Pool",
    ),
    "NOTIFICATION_POOL_SCHEDULING_EMAIL_RCPTS": (
        "",
        "Additional email recipients for Scheduling Pool",
    ),
    "NOTIFICATION_POOL_TQA_EMAIL_RCPTS": (
        "",
        "Additional email recipients for TQA Pool",
    ),
    "NOTIFICATION_POOL_PQA_EMAIL_RCPTS": (
        "",
        "Additional email recipients for PQA Pool",
    ),
    # ResourceManager Integration
    "RM_SYNC_ENABLED": (False, "Should RM Synchronisation be enabled"),
    "RM_SYNC_API_TOKEN": ("", "Developer API Token"),
    "RM_SYNC_API_SITE": ("https://api.rm.smartsheet.com", "Domain of RM API"),
    "RM_WARNING_MSG": (
        "This project is managed via CHAOTICA.",
        "Warning message to display in project descriptions.",
    ),
    "RM_SYNC_STALE_TIMEOUT": (60, "Amount of minutes before a sync task is stale"),
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

GUARDIAN_RAISE_403 = False
GUARDIAN_RENDER_403 = True
GUARDIAN_TEMPLATE_403 = "403.html"

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
    # "django.contrib.sessions",
    "qsessions",
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
    "django_clamav",
    "crispy_forms",
    "crispy_bootstrap5",
    "django_bleach",
    "django_fsm",
    "phonenumber_field",
    "simple_history",
    "rest_framework",
    "django_filters",
    "rest_framework_datatables",
    "impersonate",
    "import_export",
    "explorer",
    "bootstrap_datepicker_plus",
    "location_field.apps.DefaultConfig",
    "storages",
    "django_cron",
    "dbbackup",  # django-dbbackup
    "corsheaders",
    "csp",
]
LOCAL_APPS = [
    "chaotica_utils",
    "jobtracker",
    "reporting",
    "notifications",
    "dashboard",
    "rm_sync",
]

INSTALLED_APPS = DEFAULT_APPS + THIRD_PARTY_APPS + LOCAL_APPS

if DEBUG:
    INSTALLED_APPS += [
        "debug_toolbar",
    ]

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
    "br",
    "img",
    "div",
    "table",
    "tr",
    "td",
]
# Which HTML attributes are allowed
BLEACH_ALLOWED_ATTRIBUTES = ["href", "title", "style", "src"]
# Which CSS properties are allowed in 'style' attributes (assuming style is
# an allowed attribute)
BLEACH_ALLOWED_STYLES = [
    "font-family",
    "text-align",
    "font-weight",
    "text-decoration",
    "font-variant",
    "width",
    "height",
]
# Which protocols (and pseudo-protocols) are allowed in 'src' attributes
# (assuming src is an allowed attribute)
BLEACH_ALLOWED_PROTOCOLS = ["http", "https", "data"]
BOOTSTRAP_DATEPICKER_PLUS = {
    "app_static_url": f"{SITE_PROTO}://{SITE_DOMAIN}/static/vendors/bootstrap_datepicker_plus/",
    "options": {
        "allowInputToggle": True,
    },
    "variant_options": {
        "date": {
            "format": "YYYY-MM-DD",
        },
    },
}
DJANGO_CRON_DELETE_LOGS_OLDER_THAN = 14
DJANGO_CRON_LOCK_BACKEND = "django_cron.backends.lock.file.FileLock"
CRON_CLASSES = [
    "notifications.tasks.task_send_email_notifications",
    "chaotica_utils.tasks.task_clean_historical_records",
    "chaotica_utils.tasks.task_sync_global_permissions",
    "chaotica_utils.tasks.task_sync_role_permissions_to_default",
    "chaotica_utils.tasks.task_sync_role_permissions",
    "chaotica_utils.tasks.task_backup_site",
    "jobtracker.tasks.task_progress_workflows",
    "jobtracker.tasks.task_fire_job_notifications",
    "jobtracker.tasks.task_fire_onboarding_reminders",
    "rm_sync.tasks.task_sync_rm_schedule",
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
        "rest_framework_datatables.renderers.DatatablesRenderer",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "rest_framework_datatables.filters.DatatablesFilterBackend",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework_datatables.pagination.DatatablesPageNumberPagination",
    # 'PAGE_SIZE': 50
}
SESSION_ENGINE = "qsessions.backends.db"
MIDDLEWARE = [
    "chaotica_utils.middleware.HealthCheckMiddleware",
    "chaotica_utils.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "csp.middleware.CSPMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    # 'django.middleware.cache.UpdateCacheMiddleware',
    # 'django.middleware.common.CommonMiddleware',
    # 'django.middleware.cache.FetchFromCacheMiddleware',
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "impersonate.middleware.ImpersonateMiddleware",
    "chaotica_utils.middleware.NewInstallMiddleware",
    "chaotica_utils.middleware.MaintenanceModeMiddleware",
]

if DEBUG:
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")

# CACHE_MIDDLEWARE_ALIAS  = ' ' # cache alias
CACHE_MIDDLEWARE_SECONDS = 600  # number of seconds each page should be cached.
CACHE_MIDDLEWARE_KEY_PREFIX = ""  # name of site if multiple sites are used

ROOT_URLCONF = "chaotica.urls"

INTERNAL_IPS = [
    "127.0.0.1",
]

# Define trusted proxy networks
# Only requests from these IPs/networks will have their forwarded headers trusted
TRUSTED_PROXIES = [
    "10.0.0.0/8",  # Private network where load balancer might be
    "172.16.0.0/12",  # Private network
    "192.168.0.0/16",  # Private network
    "127.0.0.1/32",  # Localhost
    # Add specific proxy/load balancer IPs here:
    # '203.0.113.0/24',    # Example: CDN/proxy network
    # '198.51.100.1/32',   # Example: specific proxy server
]

# Additional security settings
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # If behind HTTPS proxy
USE_X_FORWARDED_HOST = False  # Only enable if you trust your proxy
USE_X_FORWARDED_PORT = False  # Only enable if you trust your proxy


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
                "csp.context_processors.nonce",
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

if not os.environ.get("SQL_ENGINE", None):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.path.join(BASE_DIR, "db.sqlite3"),
            "OPTIONS": {
                "timeout": 20,
            },
        }
    }
else:
    db_options = {}

    if os.environ.get("RDS_TLS_USE", False):
        db_options["ssl"] = {
            "ca": os.environ.get("RDS_TLS_CA_PATH", "/app/ca-cert.pem")
        }

    DATABASES = {
        "default": {
            "ENGINE": os.environ.get("SQL_ENGINE", "django.db.backends.sqlite3"),
            "NAME": os.environ.get("RDS_DB_NAME", os.path.join(BASE_DIR, "db.sqlite3")),
            "USER": os.environ.get("RDS_USERNAME", "root"),
            "PASSWORD": os.environ.get("RDS_PASSWORD", "chaoticadb1"),
            "HOST": os.environ.get("RDS_HOSTNAME", "127.0.0.1"),
            "PORT": os.environ.get("RDS_PORT", "13306"),
            "DEFAULT-CHARACTER-SET": "utf8",
            "OPTIONS": db_options,
        }
    }


CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'IGNORE_EXCEPTIONS': True,  # This is crucial for preventing 50x errors
            'CONNECTION_POOL_KWARGS': {  # This syntax works with django-redis
                'max_connections': 50,
                'retry_on_timeout': True,
                'socket_connect_timeout': 5,
                'socket_timeout': 5,
            },
            'PICKLE_VERSION': -1,
        }
    }
}
CONSTANCE_DATABASE_CACHE_BACKEND = 'default'


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
TIME_ZONE = os.environ.get("TZ", default="UTC")
USE_I18N = True
USE_L10N = True
USE_TZ = True

# Backups
DBBACKUP_CLEANUP_KEEP = os.environ.get("DBBACKUP_CLEANUP_KEEP", default=60)
DBBACKUP_CLEANUP_KEEP_MEDIA = os.environ.get("DBBACKUP_CLEANUP_KEEP_MEDIA", default=60)

DBBACKUP_ENABLED = os.environ.get("DBBACKUP_ENABLED", default=False)
if DBBACKUP_ENABLED == "1" or DBBACKUP_ENABLED:
    DBBACKUP_STORAGE = os.environ.get(
        "DBBACKUP_STORAGE", default="django.core.files.storage.FileSystemStorage"
    )
    if "FileSystemStorage" in DBBACKUP_STORAGE:
        DBBACKUP_STORAGE_OPTIONS = {
            "location": os.environ.get("DBBACKUP_FS_LOCATION", default="")
        }
    if "S3Boto3Storage" in DBBACKUP_STORAGE:
        DBBACKUP_STORAGE_OPTIONS = {
            "access_key": os.environ.get("DBBACKUP_S3_AKEY", default=""),
            "secret_key": os.environ.get("DBBACKUP_S3_SKEY", default=""),
            "bucket_name": os.environ.get("DBBACKUP_S3_BUCKET_NAME", default=""),
            "default_acl": os.environ.get("DBBACKUP_S3_DEFAULT_ACL", default=""),
        }

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


STATICFILES_LOCATION = "static"
MEDIAFILES_LOCATION = "media"
TINYMCE_JS_URL = "vendors/tinymce/tinymce.min.js"

STATIC_BACKEND = "django.contrib.staticfiles.storage.StaticFilesStorage"
MEDIA_BACKEND = "django.core.files.storage.FileSystemStorage"
USE_S3 = os.environ.get("USE_S3", default=False)
AWS_S3_CUSTOM_DOMAIN = os.getenv("AWS_S3_CUSTOM_DOMAIN", None)

if USE_S3 == "1" or USE_S3:
    STATIC_BACKEND = "storages.backends.s3.S3Storage"
    MEDIA_BACKEND = "storages.backends.s3.S3Storage"
    DEFAULT_S3_STORAGE_OPTIONS = {
        "access_key": os.getenv("AWS_STORAGE_ACCESS_KEY_ID"),
        "secret_key": os.getenv("AWS_STORAGE_SECRET_ACCESS_KEY"),
        "bucket_name": os.getenv("AWS_STORAGE_BUCKET_NAME"),
        # "AWS_S3_SIGNATURE_VERSION": "s3v4",
        # "AWS_S3_OBJECT_PARAMETERS": {"CacheControl": "max-age=86400"},
    }

    if AWS_S3_CUSTOM_DOMAIN:
        # Use CloudFront
        DEFAULT_S3_STORAGE_OPTIONS["custom_domain"] = AWS_S3_CUSTOM_DOMAIN
        DEFAULT_S3_STORAGE_OPTIONS["cloudfront_key"] = base64.b64decode(
            os.environ.get("AWS_CLOUDFRONT_KEY", None)
        )
        DEFAULT_S3_STORAGE_OPTIONS["cloudfront_key_id"] = os.environ.get(
            "AWS_CLOUDFRONT_KEY_ID", None
        )
        MEDIA_BACKEND = "chaotica.custom_storages.MediaStorage"
        STATIC_BACKEND = "chaotica.custom_storages.StaticStorage"
    else:
        # Use S3 directly
        DEFAULT_S3_STORAGE_OPTIONS["custom_domain"] = (
            f'{os.getenv("AWS_STORAGE_BUCKET_NAME")}.s3.amazonaws.com'
        )

    MEDIA_URL = f'https://{DEFAULT_S3_STORAGE_OPTIONS["custom_domain"]}/media/'
    STATIC_URL = f'https://{DEFAULT_S3_STORAGE_OPTIONS["custom_domain"]}/static/'

    STORAGES = {
        "default": {
            "BACKEND": STATIC_BACKEND,
            "OPTIONS": {
                # add or override options defined in default
                **DEFAULT_S3_STORAGE_OPTIONS,
                # "default_acl": "public-read",
                "file_overwrite": True,
            },
        },
        "public_media": {
            "BACKEND": MEDIA_BACKEND,
            "OPTIONS": {
                "location": "media",
            },
        },
        "staticfiles": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                # add or override options defined in default
                **DEFAULT_S3_STORAGE_OPTIONS,
                "location": "static",
            },
        },
    }
else:
    AWS_S3_CUSTOM_DOMAIN = ""
    MEDIA_URL = "/media/"
    MEDIA_ROOT = os.path.join(BASE_DIR, "mediafiles")
    STATIC_URL = "/static/"
    STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

STATICFILES_DIRS = (os.path.join(BASE_DIR, "static"),)


CORS_ALLOW_ALL_ORIGINS = True

CONTENT_SECURITY_POLICY = {
    "EXCLUDE_URL_PREFIXES": ["/excluded-path/"],
    "DIRECTIVES": {
        "default-src": [
            # FFS
            "*",
            SELF,
            # NONCE,
            # "{}".format(AWS_S3_CUSTOM_DOMAIN),
            # "https://cdnjs.cloudflare.com",
            # "https://*.fontawesome.com",
            UNSAFE_EVAL,
            UNSAFE_INLINE,
            "data:",
            "blob:",
        ],
        "upgrade-insecure-requests": True,
    },
}

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
EXPLORER_PERMISSION_VIEW = lambda r: r.user.is_superuser
EXPLORER_PERMISSION_CHANGE = lambda r: r.user.is_superuser
EXPLORER_DATA_EXPORTERS = [
    ("csv", "explorer.exporters.CSVExporter"),
    ("excel", "explorer.exporters.ExcelExporter"),
    ("json", "explorer.exporters.JSONExporter"),
]

CLAMAV_UNIX_SOCKET = "/var/run/clamav/clamd.ctl"
CLAMAV_USE_TCP = False
CLAMAV_TCP_PORT = 3310
CLAMAV_TCP_ADDR = "127.0.0.1"
