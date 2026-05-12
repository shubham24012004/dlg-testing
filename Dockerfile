FROM python:3.11-slim

# tesseract-ocr: required by pytesseract
# poppler-utils: required by pdfplumber for PDF rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps before copying source for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium browser + its OS-level dependencies in one step
RUN playwright install --with-deps chromium

# Copy application source (respects .dockerignore)
COPY . .

EXPOSE 5000

CMD ["python", "DLGDataAnalysisTool.py"]
