# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
# (Assuming a requirements.txt might exist or be added later)
# RUN pip install --no-cache-dir -r requirements.txt

# Make port 80 available to the world outside this container (if needed for UI)
# EXPOSE 80

# Define environment variable defaults (can be overridden)
ENV STATUS_DIR=/tmp/status
ENV CHECK_INTERVAL_S=5
ENV LATENCY_FILE_NAME=latency.txt

# Run kafka_demo_ui.py when the container launches
CMD ["python", "./kafka_demo_ui.py"]
