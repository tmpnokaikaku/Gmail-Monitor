FROM python:3.9-slim

ARG OCI_IMAGE_SOURCE="https://github.com/OWNER/REPOSITORY"

LABEL org.opencontainers.image.source="${OCI_IMAGE_SOURCE}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY app.py ai_extractor.py extract_gmail_content.py gmm_server.py google_service.py line_webhook.py ./
COPY scripts/ ./scripts/

CMD ["python", "-u", "app.py"]
