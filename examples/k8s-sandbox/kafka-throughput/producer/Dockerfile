FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir kafka-python

# Copy the producer script into the container
COPY producer.py /app/
# Copy the healthcheck script
COPY healthcheck.py /app/

# Set the command to run the producer script by default
CMD ["python", "./producer.py"]
