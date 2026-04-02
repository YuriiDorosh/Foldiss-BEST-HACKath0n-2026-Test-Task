FROM python:3.11-slim

WORKDIR /app

# Install system deps needed by pymavlink
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY parser/ ./parser/

CMD ["python", "main.py"]
