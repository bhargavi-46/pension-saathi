FROM python:3.11-slim

# Tesseract OCR + Hindi/Telugu/Tamil language packs — server-side OCR so
# document images never leave this box.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-hin \
    tesseract-ocr-tel \
    tesseract-ocr-tam \
    && rm -rf /var/lib/apt/lists/* \
    && tesseract --version

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# Shell form so Render's $PORT is expanded at runtime (exec form wouldn't).
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
