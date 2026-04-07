FROM nginx:alpine

# Install Python, pip, and PostgreSQL client libs
RUN apk add --no-cache python3 py3-pip postgresql-libs gcc python3-dev musl-dev postgresql-dev

# Create venv and install deps
RUN python3 -m venv /opt/venv
COPY backend/requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

# Remove build deps to reduce image size
RUN apk del gcc python3-dev musl-dev postgresql-dev

# Copy backend code
COPY backend/ /app/backend/

# Nginx config
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Frontend
COPY mip-platform.html /usr/share/nginx/html/index.html

EXPOSE 8080

CMD sh -c "cd /app/backend && /opt/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 & sleep 3 && nginx -g 'daemon off;'"
