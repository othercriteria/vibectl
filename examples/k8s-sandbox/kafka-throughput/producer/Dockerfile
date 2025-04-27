FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY producer.py .

# Add healthcheck script
COPY healthcheck.py .

CMD ["python", "./producer.py"]
