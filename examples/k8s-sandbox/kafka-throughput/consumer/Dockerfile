FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir kafka-python

# Copy the consumer script into the container
COPY consumer.py /app/
# Copy the healthcheck script
COPY healthcheck.py /app/

# Set the command to run the consumer script by default
CMD ["python", "./consumer.py"]
