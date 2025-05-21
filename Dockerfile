FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and demo page
COPY oauth-spotify.py .
COPY sample-client.html .

# Set environment variables (these will need to be provided at runtime)
ENV SPOTIFY_CLIENT_ID=""
ENV SPOTIFY_CLIENT_SECRET=""
ENV REDIRECT_URI=""
ENV PORT=4180
ENV PROXY_SECRET=""
ENV ENABLE_DEMO="false"

# Expose the port the app runs on
EXPOSE 4180

# Run the application with Gunicorn (production WSGI server)
CMD ["gunicorn", "--bind", "0.0.0.0:4180", "--workers", "4", "oauth-spotify:app"]
