# Stage 1: build React frontend
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY webapp/frontend/package*.json ./
RUN npm ci
COPY webapp/frontend/ ./
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL
ENV VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY
RUN npm run build

# Stage 2: Python runtime
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y libgomp1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY src/ ./src/
COPY webapp/backend/ ./webapp/backend/
RUN pip install --no-cache-dir -e ".[web]" psycopg2-binary "python-jose[cryptography]"
COPY --from=frontend /app/frontend/dist ./webapp/frontend/dist
ENV CELLCOUNTER_DATA=/data
EXPOSE 8000
CMD ["uvicorn", "webapp.backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
