FROM python:3.11-slim

# Install PostgreSQL client libs
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ /app/backend/

# Copy frontend
RUN mkdir -p /app/frontend/images
COPY mip-platform.html /app/frontend/index.html
COPY images/ /app/frontend/images/

EXPOSE 8080

WORKDIR /app/backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--log-level", "info"]
