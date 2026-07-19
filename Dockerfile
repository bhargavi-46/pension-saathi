FROM debian:bullseye-slim

# Install Python 3.11 + Tesseract + language packs in ONE layer
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    tesseract-ocr \
    tesseract-ocr-hin \
    tesseract-ocr-tel \
    tesseract-ocr-tam \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Verify Tesseract from the start
RUN tesseract --version && which tesseract

WORKDIR /app

# Copy and install Python dependencies
COPY backend/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY backend/ .

# Run FastAPI
CMD ["python3.11", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
