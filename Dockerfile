# Use a slim Python 3.9 image
FROM python:3.9-slim

# Install system dependencies needed for building Python packages & audio conversion
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libsndfile1 \
        ffmpeg \
        && rm -rf /var/lib/apt/lists/*

# Set a working directory
WORKDIR /app

# Copy requirements and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose port 5000
EXPOSE 5000

# Run the Flask app. We let the environment variable PORT override the default 5000
ENV PORT=5000
CMD ["python", "app.py"]
