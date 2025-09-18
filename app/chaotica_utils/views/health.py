import json
import redis
from django.http import JsonResponse
from django.views import View
from django.db import connection
from django.core.mail import send_mail
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
from constance import config
from datetime import datetime
import socket
import requests


class HealthCheckView(View):
    def get(self, request):
        # Check API key
        api_key = request.GET.get('api_key')

        # Try to validate the API key
        from ..models import HealthCheckAPIKey

        try:
            # Convert string to UUID for validation
            import uuid
            key_uuid = uuid.UUID(api_key) if api_key else None

            # Find the API key
            api_key_obj = HealthCheckAPIKey.objects.filter(
                key=key_uuid,
                is_active=True
            ).select_related('user').first()

            if not api_key_obj:
                return JsonResponse({'error': 'Invalid or inactive API key'}, status=401)

            # Check if user is active and has proper permissions (superuser or staff)
            if not api_key_obj.user.is_active:
                return JsonResponse({'error': 'User account is inactive'}, status=401)

            if not (api_key_obj.user.is_superuser or api_key_obj.user.is_staff):
                return JsonResponse({'error': 'Insufficient permissions'}, status=403)

            # Mark the API key as used
            api_key_obj.mark_used()

        except Exception as e:
            return JsonResponse({'error': 'Authentication error'}, status=401)

        health_status = {
            'status': 'healthy',
            'timestamp': timezone.now().isoformat(),
            'checks': {}
        }

        # Database check
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            health_status['checks']['database'] = {
                'status': 'ok',
                'backend': connection.settings_dict['ENGINE'].split('.')[-1]
            }
        except Exception as e:
            health_status['checks']['database'] = {
                'status': 'error',
                'error': str(e)
            }
            health_status['status'] = 'unhealthy'

        # Redis/Cache check
        try:
            cache_key = f'health_check_{timezone.now().timestamp()}'
            cache.set(cache_key, 'test', 5)
            cache_value = cache.get(cache_key)
            cache.delete(cache_key)

            if cache_value == 'test':
                health_status['checks']['cache'] = {
                    'status': 'ok',
                    'backend': 'redis'
                }
            else:
                raise Exception("Cache test value mismatch")
        except Exception as e:
            health_status['checks']['cache'] = {
                'status': 'error',
                'error': str(e)
            }
            health_status['status'] = 'unhealthy'

        # Email check (only test configuration, don't actually send)
        try:
            if settings.EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend":
                health_status['checks']['email'] = {
                    'backend': settings.EMAIL_BACKEND,
                    'host': settings.EMAIL_HOST,
                    'port': settings.EMAIL_PORT,
                    'use_tls': settings.EMAIL_USE_TLS,
                    'enabled': 'ok' if config.EMAIL_ENABLED else 'disabled'
                }

            # Test SMTP connection if using SMTP backend
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(5)
                    result = sock.connect_ex((settings.EMAIL_HOST, int(settings.EMAIL_PORT)))
                    sock.close()

                    if result == 0:
                        health_status['checks']['email']['connectivity'] = 'ok'
                        health_status['checks']['email']['status'] = 'ok'
                    else:
                        health_status['checks']['email']['connectivity'] = 'port_closed'
                        health_status['checks']['email']['status'] = 'warning'
                except Exception as conn_error:
                    health_status['checks']['email']['connectivity'] = 'unreachable'
                    health_status['checks']['email']['connectivity_error'] = str(conn_error)
                    health_status['checks']['email']['status'] = 'warning'

        except Exception as e:
            health_status['checks']['email'] = {
                'status': 'error',
                'error': str(e)
            }
            health_status['status'] = 'unhealthy'

        # RM Sync check
        try:
            rm_sync_enabled = config.RM_SYNC_ENABLED
            health_status['checks']['rm_sync'] = {
                'status': 'ok' if rm_sync_enabled else 'disabled'
            }
            rm_api_site = config.RM_SYNC_API_SITE
            rm_api_token = config.RM_SYNC_API_TOKEN
            health_status['checks']['rm_sync']['api_site'] = rm_api_site
            health_status['checks']['rm_sync']['has_token'] = bool(rm_api_token)

            if rm_api_site and rm_api_token:
                # Test connectivity to RM API (without making actual API calls)
                try:
                    response = requests.head(rm_api_site, timeout=5)
                    health_status['checks']['rm_sync']['api_status'] = response.status_code
                except requests.RequestException as req_error:
                    health_status['checks']['rm_sync']['api_status'] = False
                    health_status['checks']['rm_sync']['connectivity_error'] = str(req_error)
                    health_status['checks']['rm_sync']['status'] = 'warning'

        except Exception as e:
            health_status['checks']['rm_sync'] = {
                'status': 'error',
                'error': str(e)
            }

        # File storage check
        try:
            from django.core.files.storage import default_storage
            from django.core.files.base import ContentFile

            # Check if we can access the media storage
            test_file_name = f'.health_check_{timezone.now().timestamp()}.txt'
            test_content = ContentFile(b'health check')

            # Write test file
            path = default_storage.save(test_file_name, test_content)

            # Check if file exists and delete it
            exists = default_storage.exists(path)
            default_storage.delete(path)

            if exists:
                health_status['checks']['storage'] = {
                    'status': 'ok',
                    'backend': default_storage.__class__.__name__
                }
            else:
                raise Exception("Test file not found after save")

        except Exception as e:
            health_status['checks']['storage'] = {
                'status': 'error',
                'error': str(e)
            }
            health_status['status'] = 'unhealthy'

        # ClamAV check (if configured)
        try:
            if hasattr(settings, 'CLAMAV_ENABLED') and settings.CLAMAV_ENABLED:
                from django_clamav import get_scanner

                scanner = get_scanner()
                if scanner.ping():
                    health_status['checks']['clamav'] = {
                        'status': 'ok',
                        'enabled': True
                    }
                else:
                    health_status['checks']['clamav'] = {
                        'status': 'error',
                        'enabled': True,
                        'error': 'Cannot ping ClamAV daemon'
                    }
            else:
                health_status['checks']['clamav'] = {
                    'status': 'disabled',
                    'enabled': False
                }
        except ImportError:
            health_status['checks']['clamav'] = {
                'status': 'not_installed',
                'enabled': False
            }
        except Exception as e:
            health_status['checks']['clamav'] = {
                'status': 'error',
                'error': str(e)
            }

        # Azure AD / ADFS SSO check
        try:
            adfs_enabled = config.ADFS_ENABLED
            health_status['checks']['sso_adfs'] = {
                'enabled': adfs_enabled,
                'status': 'ok' if adfs_enabled else 'disabled'
            }

            if adfs_enabled:
                from django.conf import settings as django_settings

                # Check ADFS configuration - these come from AUTH_ADFS dict in settings
                adfs_config = getattr(django_settings, 'AUTH_ADFS', {})
                tenant_id = adfs_config.get('TENANT_ID', '')
                client_id = adfs_config.get('CLIENT_ID', '')
                client_secret = adfs_config.get('CLIENT_SECRET', '')

                health_status['checks']['sso_adfs']['tenant_id'] = tenant_id if tenant_id != 'xx' else 'not_configured'
                health_status['checks']['sso_adfs']['client_id'] = client_id if client_id != 'xx' else 'not_configured'
                health_status['checks']['sso_adfs']['has_secret'] = bool(client_secret and client_secret != 'xx')
                health_status['checks']['sso_adfs']['auto_login'] = config.ADFS_AUTO_LOGIN

                # Check if configuration is valid
                if tenant_id == 'xx' or client_id == 'xx' or client_secret == 'xx':
                    health_status['checks']['sso_adfs']['status'] = 'error'
                    health_status['checks']['sso_adfs']['error'] = 'ADFS not properly configured'
                    health_status['status'] = 'unhealthy'
                else:
                    # Test Azure AD connectivity (OpenID configuration endpoint)
                    try:
                        openid_url = f'https://login.microsoftonline.com/{tenant_id}/v2.0/.well-known/openid-configuration'
                        response = requests.get(openid_url, timeout=5)

                        if response.status_code == 200:
                            health_status['checks']['sso_adfs']['azure_ad_reachable'] = True
                            health_status['checks']['sso_adfs']['openid_config'] = 'accessible'

                            # Try to validate credentials by requesting a token
                            # This uses client credentials flow to test if the app registration is valid
                            try:
                                token_url = f'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token'
                                token_data = {
                                    'grant_type': 'client_credentials',
                                    'client_id': client_id,
                                    'client_secret': client_secret,
                                    'scope': 'https://graph.microsoft.com/.default'
                                }

                                token_response = requests.post(token_url, data=token_data, timeout=5)

                                if token_response.status_code == 200:
                                    health_status['checks']['sso_adfs']['credentials_valid'] = True
                                    health_status['checks']['sso_adfs']['token_obtainable'] = True
                                else:
                                    health_status['checks']['sso_adfs']['credentials_valid'] = False
                                    health_status['checks']['sso_adfs']['token_error'] = token_response.status_code

                                    # Parse error response if available
                                    try:
                                        error_data = token_response.json()
                                        health_status['checks']['sso_adfs']['token_error_description'] = error_data.get('error_description', error_data.get('error', 'Unknown error'))
                                    except:
                                        health_status['checks']['sso_adfs']['token_error_description'] = token_response.text[:200] if token_response.text else 'No error details'

                                    health_status['checks']['sso_adfs']['status'] = 'warning'
                            except requests.RequestException as token_error:
                                health_status['checks']['sso_adfs']['credentials_valid'] = 'unknown'
                                health_status['checks']['sso_adfs']['token_test_error'] = str(token_error)
                                health_status['checks']['sso_adfs']['status'] = 'warning'
                        else:
                            health_status['checks']['sso_adfs']['azure_ad_reachable'] = False
                            health_status['checks']['sso_adfs']['openid_config_status'] = response.status_code
                            health_status['checks']['sso_adfs']['status'] = 'warning'
                    except requests.RequestException as req_error:
                        health_status['checks']['sso_adfs']['azure_ad_reachable'] = False
                        health_status['checks']['sso_adfs']['connectivity_error'] = str(req_error)
                        health_status['checks']['sso_adfs']['status'] = 'warning'

        except Exception as e:
            health_status['checks']['sso_adfs'] = {
                'status': 'error',
                'error': str(e)
            }

        # Application metrics
        try:
            from django.contrib.auth import get_user_model
            from jobtracker.models import Job, Phase
            from jobtracker.enums import JobStatuses, PhaseStatuses
            from notifications.models import Notification

            User = get_user_model()

            health_status['metrics'] = {
                'users': {
                    'total': User.objects.count(),
                    'active': User.objects.filter(is_active=True).count(),
                    'with_roles': User.objects.filter(is_active=True, groups__isnull=False).count()
                },
                'jobs': {
                    'total': Job.objects.count(),
                    'active': Job.objects.filter(status__in=JobStatuses.ACTIVE_STATUSES).count()
                },
                'phases': {
                    'total': Phase.objects.count(),
                    'active': Job.objects.filter(status__in=PhaseStatuses.ACTIVE_STATUSES).count()
                },
                'notifications': {
                    'pending': Notification.objects.filter(is_emailed=False).count()
                }
            }
        except Exception as e:
            health_status['metrics'] = {
                'status': 'error',
                'error': str(e)
            }

        # Cron job status check
        try:
            from django_cron.models import CronJobLog
            from datetime import timedelta

            cron_status = {}

            # Get configured cron jobs
            configured_jobs = settings.CRON_CLASSES

            for cron_class_path in configured_jobs:
                job_code = cron_class_path.split('.')[-1]

                # Get the actual cron job code from the class
                try:
                    module_path, class_name = cron_class_path.rsplit('.', 1)
                    module = __import__(module_path, fromlist=[class_name])
                    cron_class = getattr(module, class_name)
                    job_code = cron_class.code
                except:
                    pass  # Use the extracted name if we can't import the class

                # Get latest log entry for this job
                latest_log = CronJobLog.objects.filter(code=job_code).order_by('-start_time').first()

                if latest_log:
                    job_info = {
                        'last_run': latest_log.start_time.isoformat() if latest_log.start_time else None,
                        'last_success': latest_log.is_success,
                        'run_time_seconds': latest_log.run_time if hasattr(latest_log, 'run_time') else None,
                    }

                    # Check if job is overdue based on schedule
                    if latest_log.start_time:
                        time_since_run = timezone.now() - latest_log.start_time

                        # Try to determine expected frequency
                        try:
                            module_path, class_name = cron_class_path.rsplit('.', 1)
                            module = __import__(module_path, fromlist=[class_name])
                            cron_class = getattr(module, class_name)

                            # Check for RUN_EVERY_MINS
                            if hasattr(cron_class, 'RUN_EVERY_MINS'):
                                expected_interval = timedelta(minutes=cron_class.RUN_EVERY_MINS)
                                job_info['expected_interval_minutes'] = cron_class.RUN_EVERY_MINS
                                job_info['overdue'] = time_since_run > (expected_interval * 2)  # Allow 2x the interval before marking overdue
                            # Check for RUN_AT_TIMES
                            elif hasattr(cron_class, 'RUN_AT_TIMES'):
                                # For scheduled times, check if it's been more than 25 hours since last run
                                job_info['scheduled_times'] = cron_class.RUN_AT_TIMES
                                job_info['overdue'] = time_since_run > timedelta(hours=25)
                            else:
                                job_info['overdue'] = False
                        except:
                            # Default: consider overdue if not run in 25 hours
                            job_info['overdue'] = time_since_run > timedelta(hours=25)

                        job_info['hours_since_last_run'] = round(time_since_run.total_seconds() / 3600, 2)

                    # Add failure count
                    recent_failures = CronJobLog.objects.filter(
                        code=job_code,
                        is_success=False,
                        start_time__gte=timezone.now() - timedelta(days=1)
                    ).count()

                    if recent_failures > 0:
                        job_info['recent_failures_24h'] = recent_failures
                        job_info['status'] = 'warning'
                    elif job_info.get('overdue'):
                        job_info['status'] = 'warning'
                    else:
                        job_info['status'] = 'ok'
                else:
                    job_info = {
                        'status': 'never_run',
                        'last_run': None
                    }

                cron_status[job_code] = job_info

            # Overall cron health
            has_failures = any(job.get('status') == 'warning' for job in cron_status.values())
            never_run = any(job.get('status') == 'never_run' for job in cron_status.values())

            health_status['checks']['cron_jobs'] = {
                'status': 'warning' if (has_failures or never_run) else 'ok',
                'total_jobs': len(configured_jobs),
                'jobs': cron_status
            }

            if has_failures:
                health_status['checks']['cron_jobs']['has_failures'] = True
            if never_run:
                health_status['checks']['cron_jobs']['has_never_run'] = True

        except ImportError:
            health_status['checks']['cron_jobs'] = {
                'status': 'error',
                'error': 'django_cron not installed'
            }
        except Exception as e:
            health_status['checks']['cron_jobs'] = {
                'status': 'error',
                'error': str(e)
            }

        # Set overall status
        if any(check.get('status') == 'error' for check in health_status['checks'].values()):
            health_status['status'] = 'unhealthy'
        elif any(check.get('status') == 'warning' for check in health_status['checks'].values()):
            health_status['status'] = 'degraded'

        # Return appropriate status code
        status_code = 200 if health_status['status'] == 'healthy' else 503

        return JsonResponse(health_status, status=status_code, json_dumps_params={'indent': 2})