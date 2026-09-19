"""
Shared MongoDB client for all SyllaByte agents.

Collections (created lazily on first insert):
  - knowledge_units      : nodes of the Knowledge Unit Graph
  - ku_edges             : prerequisite edges between KUs
  - student_profiles     : per-student, per-KU readiness levels
  - jobs                 : Celery job metadata / status tracking
  - assessment_items     : CAT item bank (question, alpha, beta, KU id)
"""

import os
from functools import lru_cache

from pymongo import MongoClient
from pymongo.database import Database

MONGO_URI = os.environ.get("SYLLABYTE_MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.environ.get("SYLLABYTE_MONGO_DB", "syllabyte")


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    return MongoClient(MONGO_URI)


def get_db() -> Database:
    return get_client()[MONGO_DB_NAME]


def ping() -> bool:
    """Quick health check — call this once during setup to confirm connectivity."""
    try:
        get_client().admin.command("ping")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[db] MongoDB ping failed: {e}")
        return False


if __name__ == "__main__":
    ok = ping()
    print(f"MongoDB reachable: {ok}")
