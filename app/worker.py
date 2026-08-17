from celery import Celery
from celery.schedules import crontab

from app.core.config import settings


celery_app = Celery(
    "wakelock_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.plan_tasks"],
)

celery_app.conf.update(
    broker_use_ssl={
        "ssl_cert_reqs": "CERT_REQUIRED",
    },
    redis_backend_use_ssl={
        "ssl_cert_reqs": "CERT_REQUIRED",
    },
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    beat_schedule={
        "check-alarms-every-minute": {
            "task": "app.tasks.plan_tasks.process_due_alarms",
            "schedule": crontab(minute="*"),
        },
        "check-completed-plans-daily": {
            "task": "app.tasks.plan_tasks.check_completed_plans",
            "schedule": crontab(hour="0", minute="5"),
        },
    },
)

celery_app.autodiscover_tasks(["app.tasks"])
