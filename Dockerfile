# Fire Simulator image: the simulation API and the built command-center UI in one container.
#   build:  python build.py package        (or: docker build -t firesim:local .)
#   run:    docker run -p 8000:8000 firesim:local   ->  http://localhost:8000

# ---- Stage 1: type-check and bundle the UI ------------------------------------------
FROM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python runtime serving the API and the UI -----------------------------
FROM python:3.12-slim
LABEL org.opencontainers.image.source="https://github.com/jaiswaladitneu/FireSimulator" \
      org.opencontainers.image.description="Fire Simulator: simulation API and incident command center UI" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FIRESIM_STATIC_DIR=/app/static \
    FIRESIM_INCIDENTS_FILE=/app/data/incidents.json

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY engine ./engine
COPY messaging ./messaging
COPY persistence ./persistence
COPY api ./api
COPY --from=ui /ui/dist ./static

# Run as an unprivileged user; the incident history lives in /app/data (a volume in compose).
RUN useradd --create-home --uid 10001 firesim && mkdir -p /app/data && chown firesim /app/data
USER firesim

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
