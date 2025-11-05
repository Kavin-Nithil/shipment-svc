from django.urls import path
from django.http import JsonResponse
from django.db import connection
from django.conf import settings
import pika


def health_check(request):
    """Basic health check"""
    return JsonResponse({
        'status': 'healthy',
        'service': 'shipping-service',
        'version': '1.0.0'
    })


def health_ready(request):
    """Readiness check - checks database and RabbitMQ"""
    checks = {
        'database': False,
        'rabbitmq': False
    }

    # Check database
    try:
        connection.ensure_connection()
        checks['database'] = True
    except Exception as e:
        checks['database_error'] = str(e)

    # Check RabbitMQ
    if settings.RABBITMQ_ENABLED:
        try:
            credentials = pika.PlainCredentials(
                settings.RABBITMQ_USER,
                settings.RABBITMQ_PASSWORD
            )
            parameters = pika.ConnectionParameters(
                host=settings.RABBITMQ_HOST,
                port=settings.RABBITMQ_PORT,
                credentials=credentials,
                connection_attempts=1,
                socket_timeout=2
            )
            conn = pika.BlockingConnection(parameters)
            conn.close()
            checks['rabbitmq'] = True
        except Exception as e:
            checks['rabbitmq_error'] = str(e)
    else:
        checks['rabbitmq'] = 'disabled'

    is_ready = checks['database'] and (checks['rabbitmq'] or checks['rabbitmq'] == 'disabled')
    status_code = 200 if is_ready else 503

    return JsonResponse({
        'status': 'ready' if is_ready else 'not_ready',
        'checks': checks
    }, status=status_code)


def health_live(request):
    """Liveness check - simple alive check"""
    return JsonResponse({
        'status': 'alive',
        'service': 'shipping-service'
    })


urlpatterns = [
    path('', health_check, name='health'),
    path("admin/", admin.site.urls),
    path('ready/', health_ready, name='health-ready'),
    path('live/', health_live, name='health-live'),
]