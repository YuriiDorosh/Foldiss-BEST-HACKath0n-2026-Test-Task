# AI Worker — Qwen2.5-1.5B-Instruct + LoRA fine-tune (CPU-only)
FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps (PyTorch CPU-only wheel to keep image smaller)
COPY requirements.txt .
RUN pip install --no-cache-dir \
    torch==2.3.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .
COPY ai/ ./ai/

# Volumes mounted at runtime:
#   /model_cache   — HuggingFace model cache (avoids re-download)
#   /adapters      — LoRA adapter directory

CMD ["python", "main.py"]
