# Network Device Standards — shared API server
# Small, production-lean image. Build once, run anywhere Docker runs.
#
# IMPORTANT: build this from the REPOSITORY ROOT so it can see both app/ and
# server/, e.g.:   docker build -f server/Dockerfile -t nds-api .
# (docker-compose.yml already does this for you.)

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (layer caching: deps rarely change)
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the server code and the app file, preserving the repo layout
# (server.py looks for ../app/index.html relative to itself).
COPY server/ ./server/
COPY app/ ./app/

# The database lives here; mount a volume on this path to keep data between runs
RUN mkdir -p /data
ENV NDS_DB_PATH=/data/nds.db

EXPOSE 8000

# server.py is in ./server, so point uvicorn at it
WORKDIR /app/server
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
