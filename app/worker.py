from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "wakelock_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.plan_tasks"]
)

from celery.schedules import crontab

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata", 
    enable_utc=True,
    beat_schedule={
        "check-alarms-every-minute": {
            "task": "app.tasks.plan_tasks.process_due_alarms",
            "schedule": crontab(minute="*"), # Run exactly on the 0th second of every minute
        }
    }
)

# Placeholder for discovering tasks later
celery_app.autodiscover_tasks(["app.tasks"])
