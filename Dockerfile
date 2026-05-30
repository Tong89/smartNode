# ============================================================
# SmartNode — Multi-stage Dockerfile (production)
# ============================================================
# Stage 1: builder — install locked dependencies into a venv
# Stage 2: runtime — slim image, non-root user, gunicorn WSGI
# ============================================================

# ------ Stage 1: builder -----------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools needed by some wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy only the dependency manifests first (layer-cache friendly)
COPY requirements.txt ./

# Create an isolated virtualenv and install locked runtime deps + gunicorn
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip --no-cache-dir \
    && /opt/venv/bin/pip install --no-cache-dir --require-hashes -r requirements.txt \
    && /opt/venv/bin/pip install --no-cache-dir "gunicorn>=22.0,<24.0"


# ------ Stage 2: runtime -----------------------------------------------
FROM python:3.11-slim AS runtime

LABEL org.opencontainers.image.title="SmartNode" \
      org.opencontainers.image.description="Space-Based Intelligent Relay Simulation Platform" \
      org.opencontainers.image.source="https://github.com/Tong89/smartNode"

# Runtime system dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user/group for the application
RUN groupadd --gid 1001 smartnode \
    && useradd --uid 1001 --gid smartnode --shell /bin/bash --create-home smartnode

# Copy the pre-built virtualenv from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Ensure the venv is on PATH
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy application source code (respects .dockerignore)
COPY --chown=smartnode:smartnode . .

# Copy and configure the entrypoint script
COPY --chown=smartnode:smartnode docker/entrypoint.sh /app/docker/entrypoint.sh
RUN chmod +x /app/docker/entrypoint.sh

# Switch to non-root user
USER smartnode

# Expose the default service port
EXPOSE 5000

# Use tini as PID-1 (proper signal propagation and zombie reaping)
ENTRYPOINT ["tini", "--", "/app/docker/entrypoint.sh"]
