"""Celery worker. Start with: celery -A app.worker worker"""

import uuid

from celery import Celery

from app.config import get_settings
from app.pipeline.runner import run_validation

celery_app = Celery("acadledger", broker=get_settings().redis_url)
celery_app.conf.update(
    task_ignore_result=True,
    # Acknowledge only after the task finishes, so a file is not lost if the worker dies mid-run.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)


@celery_app.task(name="uploads.validate")
def validate_upload(upload_id: str) -> None:
    run_validation(uuid.UUID(upload_id))


def enqueue_validation(upload_id: uuid.UUID) -> None:
    validate_upload.apply_async(args=[str(upload_id)], retry=False)
