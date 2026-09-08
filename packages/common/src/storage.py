"""
Shared object storage client for lecture media, rendered videos, and
intermediate artifacts (Manim frames, transcripts, etc).

Uses boto3's S3 API, which works identically against:
  - AWS S3 (production / pilot deployment)
  - MinIO (local dev — S3-compatible, runs in Docker, no AWS account needed)

Set SYLLABYTE_S3_ENDPOINT to a MinIO URL (e.g. http://localhost:9000) for
local dev; leave unset to hit real AWS S3.
"""

import os
from functools import lru_cache

import boto3
from botocore.client import Config

BUCKET_NAME = os.environ.get("SYLLABYTE_BUCKET", "syllabyte-dev")
ENDPOINT_URL = os.environ.get("SYLLABYTE_S3_ENDPOINT")  # None => real AWS
AWS_ACCESS_KEY = os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin")
AWS_SECRET_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")


@lru_cache(maxsize=1)
def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=ENDPOINT_URL,
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=AWS_REGION,
        config=Config(signature_version="s3v4"),
    )


def ensure_bucket_exists(bucket: str = BUCKET_NAME) -> None:
    client = get_s3_client()
    existing = [b["Name"] for b in client.list_buckets().get("Buckets", [])]
    if bucket not in existing:
        client.create_bucket(Bucket=bucket)


def upload_file(local_path: str, key: str, bucket: str = BUCKET_NAME) -> str:
    """Upload a local file and return its storage key."""
    ensure_bucket_exists(bucket)
    get_s3_client().upload_file(local_path, bucket, key)
    return key


def download_file(key: str, local_path: str, bucket: str = BUCKET_NAME) -> str:
    get_s3_client().download_file(bucket, key, local_path)
    return local_path


if __name__ == "__main__":
    ensure_bucket_exists()
    print(f"Bucket '{BUCKET_NAME}' ready at endpoint: {ENDPOINT_URL or 'AWS S3 (default)'}")
