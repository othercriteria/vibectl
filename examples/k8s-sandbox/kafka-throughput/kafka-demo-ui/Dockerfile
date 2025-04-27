# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8081

# Define environment variable defaults (can be overridden)
ENV STATUS_DIR=/tmp/status
ENV CHECK_INTERVAL_S=5
ENV LATENCY_FILE_NAME=latency.txt

# Run the application
CMD ["python", "app.py"]
