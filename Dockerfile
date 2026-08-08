# Stage 1: Build React Frontend SPA
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Production Runtime with Python, FastAPI & FFmpeg
FROM python:3.12-slim
WORKDIR /app

# Install system dependencies & FFmpeg for lossless AV1/MP4 video/audio stream merging
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python backend requirements
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium and system dependencies
RUN playwright install chromium --with-deps

# Copy Python backend application logic
COPY backend/ ./

# Copy compiled React static web UI from Stage 1 builder
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Initialize VDO download storage folder inside container
RUN mkdir -p /app/VDO

EXPOSE 8000

# Start Uvicorn application server on all network interfaces
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
