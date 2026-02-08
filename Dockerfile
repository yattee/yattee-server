FROM python:3.12-slim

WORKDIR /app

# Install system dependencies including deno for yt-dlp JS challenge solving
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    unzip \
    nodejs \
    npm \
    && curl -fsSL https://deno.land/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

# Add deno to PATH
ENV DENO_INSTALL="/root/.deno"
ENV PATH="${DENO_INSTALL}/bin:${PATH}"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Git version for /info endpoint (passed during build)
ARG GIT_VERSION=""
ENV GIT_VERSION=${GIT_VERSION}

# Copy application code
COPY . .

# Install vendor JS/CSS (Alpine.js, Video.js) from npm
RUN npm install && rm -rf node_modules

# Create downloads and data directories
RUN mkdir -p /downloads /app/data /app/static

# Environment variables
ENV HOST=0.0.0.0
ENV PORT=8085
ENV DOWNLOAD_DIR=/downloads
ENV DATA_DIR=/app/data

# Optional: auto-provisioning (set via docker-compose or .env)
# ADMIN_USERNAME + ADMIN_PASSWORD - auto-create/update admin user on startup
# INVIDIOUS_INSTANCE_URL - configure Invidious instance and enable proxy

EXPOSE 8085

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8085", "--log-level", "info"]
