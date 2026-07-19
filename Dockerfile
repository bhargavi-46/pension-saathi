FROM python:3.11-slim

# Install system dependencies including Tesseract OCR for server-side document OCR
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-hin \
    tesseract-ocr-tel \
    tesseract-ocr-tam \
    && rm -rf /var/lib/apt/lists/* \
    && which tesseract

WORKDIR /app

# Copy backend code
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# Verify Tesseract is installed and accessible
RUN tesseract --version

# Run the app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
