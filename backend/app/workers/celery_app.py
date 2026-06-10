from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "traceworks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)
celery_app.conf.task_default_queue = "default"
celery_app.autodiscover_tasks(["app.workers"])
