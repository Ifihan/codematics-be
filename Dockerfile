FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

# Copy all files (needed for package installation)
COPY . .

# Install Python dependencies using uv
RUN uv pip install --system --no-cache .

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PYTHONPATH=/app

# Make entrypoint executable
RUN chmod +x entrypoint.sh

EXPOSE 8080

CMD ["./entrypoint.sh"]
