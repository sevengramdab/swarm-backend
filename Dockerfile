# SimplePod Surgical Strike Swarm — Control Plane Container
# =========================================================
# Like a prefab electrical panel: everything pre-wired, just
# bolt it to the wall and flip the main breaker.

FROM python:3.12-slim

# Prevent Python from writing .pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies for GPU probing and compression
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e "."

# Copy application code
COPY . .

# Create directories for runtime data
RUN mkdir -p /app/ark_backups /app/telemetry_logs /app/context_checkpoints

# Health check — the green status LED on the panel door
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Single process: FastAPI serves API + static dashboard
CMD ["python", "-m", "uvicorn", "interfaces.web_ui.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
