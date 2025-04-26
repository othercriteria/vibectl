FROM python:3.11-slim

WORKDIR /app

# No external dependencies needed for the basic overseer
# RUN pip install --no-cache-dir ...

# Copy the overseer script into the container
COPY overseer.py /app/

# Set the command to run the overseer script by default
CMD ["python", "./overseer.py"]
