# Use NVIDIA CUDA base image for GPU support (most stable version)
FROM pytorch/pytorch:2.8.0-cuda12.9-cudnn9-runtime

# Ensure non-interactive apt installs and deterministic Python output
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    ln -s /root/.local/bin/uv /usr/local/bin/uv

ENV PATH="/root/.local/bin:${PATH}"

# Set working directory
WORKDIR /app

# Copy dependency files first for better caching
COPY pyproject.toml uv.lock* ./

# Install Python dependencies with uv
# --no-dev: skip dev dependencies
# --frozen: use exact versions from lockfile (fallback to sync if no lock)
RUN uv sync --no-dev --frozen || uv sync --no-dev

# Activate the virtual environment by adding it to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY . ./

# Create upload directory expected by the app
RUN mkdir -p /app/uploads

# Expose port
EXPOSE 8000

# Default command (can be overridden in docker-compose)
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]