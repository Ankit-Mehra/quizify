# Use Python 3.12 slim image
FROM python:3.12-slim

# Create and change to the app directory
WORKDIR /app

# Install system dependencies for PDF/DOCX processing and Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    wget \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy local code to the container image
COPY . .

# Install project dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (Chromium only for web scraping)
# Note: We already installed system dependencies above, so we only need to install the browser
RUN playwright install chromium

# Run the web service on container startup
# Use shell form to allow PORT variable expansion
CMD hypercorn main:app --bind 0.0.0.0:${PORT:-8000}
