# Dockerfile for Coolify Deployment
FROM python:3.12-slim

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV TZ=Asia/Tokyo

# Install system dependencies: LibreOffice (for DOCX to PDF), cron, and essentials
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    cron \
    tzdata \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency specifications
COPY requirements.txt .

# Install Python packages and Playwright Chromium with OS dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps chromium

# Copy application source code
COPY . .

# Ensure storage directories exist
RUN mkdir -p config generated_cvs logs templates master_data

# Setup cron entrypoint script
RUN chmod +x entrypoint.sh

# Start cron daemon and stream logs
CMD ["./entrypoint.sh"]
