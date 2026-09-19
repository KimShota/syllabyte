# Ingestion Agent — syllabus parsing + Whisper transcription
FROM python:3.11-slim

# ffmpeg is required by Whisper for audio decoding
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ingestion_agent/ ./ingestion_agent/

CMD ["python", "-m", "ingestion_agent.worker"]
