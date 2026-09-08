# Animation Agent — Manim rendering environment
# Manim needs: ffmpeg, a LaTeX distribution (for math text), Cairo, Pango.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    libcairo2-dev \
    libpango1.0-dev \
    pkg-config \
    texlive \
    texlive-latex-extra \
    texlive-fonts-extra \
    texlive-science \
    tipa \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

CMD ["python", "-m", "src.worker"]
