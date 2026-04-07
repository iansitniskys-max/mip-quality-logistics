FROM nginx:alpine

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Custom nginx config optimized for SPA
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy the platform HTML
COPY mip-platform.html /usr/share/nginx/html/index.html

# Cloud Run uses PORT env var (default 8080)
EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
