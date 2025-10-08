# Use Python 3.12 slim image (smaller than full, larger than alpine but has build tools)
FROM python:3.12-slim

# Create and change to the app directory
WORKDIR /app

# Install system dependencies for PDF/DOCX processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy local code to the container image
COPY . .

# Install project dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Run the web service on container startup
# Use shell form to allow PORT variable expansion
CMD hypercorn main:app --bind 0.0.0.0:${PORT:-8000}
