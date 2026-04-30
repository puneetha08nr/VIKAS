from celery import Celery

from config.settings import settings

celery_app = Celery(
    "vikas",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        # "workers.tasks",  # uncomment as task modules are added
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Ack only after the task completes — prevents silent loss on worker crash.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Keep results for 24 h then expire.
    result_expires=86400,
)
