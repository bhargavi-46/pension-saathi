FROM python:3.11-bullseye

# Install Tesseract OCR + language packs FIRST (before Python packages)
# bullseye includes apt, gcc, build-essential needed for OCR setup
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-hin \
    tesseract-ocr-tel \
    tesseract-ocr-tam \
    && rm -rf /var/lib/apt/lists/* \
    && echo "Tesseract installed at:" \
    && which tesseract \
    && tesseract --version

WORKDIR /app

# Copy and install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# Final verification before startup
RUN echo "OCR check:" && tesseract --version && echo "Setup complete!"

# Run the FastAPI app on $PORT (Render sets this)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
