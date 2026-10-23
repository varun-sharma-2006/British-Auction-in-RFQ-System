"""Celery app: background jobs for the scaled-out deployment (REDIS_URL set).

    celery -A app.worker worker --loglevel=info      # add --pool=solo on Windows
    celery -A app.worker beat   --loglevel=info

Beat enqueues `auction.close_due` every CLOSER_INTERVAL_SECONDS; any worker
runs it. The job uses FOR UPDATE SKIP LOCKED, so several workers (or an
overlapping run) never process the same auction twice.
"""
from celery import Celery

from app.config import get_settings
from app.realtime import publish_from_worker
from app.services.closer import close_due_auctions

settings = get_settings()

celery_app = Celery("british_auction", broker=settings.redis_url or "memory://")
celery_app.conf.update(
    task_ignore_result=True,
    timezone="UTC",
    beat_schedule={
        "close-due-auctions": {
            "task": "auction.close_due",
            "schedule": settings.closer_interval_seconds,
            # A tick that couldn't run in time is useless; the next one will do the work.
            "options": {"expires": settings.closer_interval_seconds * 5},
        },
    },
)


@celery_app.task(name="auction.close_due")
def close_due() -> list[int]:
    changed = close_due_auctions()
    for rfq_id in changed:
        publish_from_worker(rfq_id, "status_changed")
    return changed
