FROM node:20-alpine AS frontend-build
WORKDIR /src/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FUTURES_DAILY_CONFIG=/app/config/config.yaml \
    FUTURES_DAILY_DB=/app/data/futures_daily.db
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
COPY config/config.yaml.example ./config/config.yaml.example
COPY --from=frontend-build /src/frontend/dist ./web/dist
RUN mkdir -p /app/data /app/logs /app/config
EXPOSE 8500
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8500"]
