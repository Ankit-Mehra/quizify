# Dockerfile for containerized deployment (Fly.io, Azure, etc.)
# For Railway/Render, this is optional - they auto-detect Python

FROM python:3.12-slim-bullseye

# Ensure all system packages are up-to-date to reduce vulnerabilities
RUN apt-get update && apt-get upgrade -y && apt-get dist-upgrade -y && apt-get clean

# Set working directory
WORKDIR /app

# Install system dependencies needed for PDF processing and web scraping
RUN apt-get update && apt-get upgrade -y && apt-get install -y \
    # For PyPDF2 and python-docx
    libpoppler-cpp-dev \
    # For Playwright (if used)
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (if web scraping is used)
# RUN playwright install chromium --with-deps

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/api/test')"

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
