# POT_PROVIDER=bundled|none — whether to include the bgutil POT provider server
ARG POT_PROVIDER=bundled

# Build the bgutil POT provider server (needs node >= 22; final image ships the
# node binary from this stage). Version must match the pip plugin pin in
# requirements.txt (bgutil-ytdlp-pot-provider).
FROM node:22-bookworm-slim AS pot-builder
ARG POT_PROVIDER_VERSION=1.3.2
ADD https://github.com/Brainicism/bgutil-ytdlp-pot-provider/archive/refs/tags/${POT_PROVIDER_VERSION}.tar.gz /tmp/pot.tar.gz
RUN mkdir -p /build \
    && tar xzf /tmp/pot.tar.gz -C /build --strip-components=1 \
    && cd /build/server \
    && npm ci --no-audit --no-fund \
    && npx tsc \
    && test -f build/main.js \
    && npm ci --omit=dev --no-audit --no-fund \
    && mkdir -p /opt/bgutil-pot-provider/bin \
    && cp -r build node_modules package.json /opt/bgutil-pot-provider/ \
    && cp /usr/local/bin/node /opt/bgutil-pot-provider/bin/node

FROM python:3.12-slim AS pot-stage-bundled
COPY --from=pot-builder /opt/bgutil-pot-provider /opt/bgutil-pot-provider

FROM python:3.12-slim AS pot-stage-none
# Empty placeholder so the final COPY succeeds without the bundle
RUN mkdir -p /opt/bgutil-pot-provider

FROM pot-stage-${POT_PROVIDER} AS pot-final

FROM python:3.12-slim

WORKDIR /app

ENV DENO_INSTALL="/opt/deno"

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
ENV PATH="${DENO_INSTALL}/bin:${PATH}"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bundled bgutil POT provider (empty dir when built with POT_PROVIDER=none)
COPY --from=pot-final /opt/bgutil-pot-provider /opt/bgutil-pot-provider

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
