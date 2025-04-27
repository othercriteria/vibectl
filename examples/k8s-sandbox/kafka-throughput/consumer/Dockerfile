FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY consumer.py .

# Add healthcheck script
COPY healthcheck.py .

CMD ["python", "./consumer.py"]
