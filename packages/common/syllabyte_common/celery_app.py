"""
Shared Celery application. Each agent registers its own tasks against this
app (e.g. ingestion_agent.tasks, script_generation_agent.tasks) so that a
single Redis-backed queue coordinates the whole pipeline:

  ingest -> assess -> generate_script -> generate_animation -> assemble_video

Run a worker for a given agent with, e.g.:
    celery -A syllabyte_common.celery_app worker -Q ingestion -l info
"""

import os

from celery import Celery

REDIS_URL = os.environ.get("SYLLABYTE_REDIS_URL", "redis://localhost:6379/0")

app = Celery(
    "syllabyte",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Dubai",
    enable_utc=True,
    task_routes={
        "ingestion_agent.*": {"queue": "ingestion"},
        "curriculum_alignment_agent.*": {"queue": "curriculum"},
        "assessment_agent.*": {"queue": "assessment"},
        "script_generation_agent.*": {"queue": "scripting"},
        "animation_agent.*": {"queue": "animation"},
    },
)

if __name__ == "__main__":
    app.start()
