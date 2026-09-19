"""
Ingestion Agent Celery worker entrypoint.
Real tasks (transcription, KUG extraction) land here in October —
this stub just proves the container boots and connects to Redis/Mongo.
"""
from ingestion_agent.syllabus_parser import parse_syllabus  # noqa: F401

if __name__ == "__main__":
    print("[ingestion_agent] worker stub running. Add Celery tasks here in October.")
