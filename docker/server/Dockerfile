FROM python:3.12-slim

WORKDIR /app

# Install dependencies separately for layer caching
COPY server/pyproject.toml ./server/pyproject.toml
RUN pip install --no-cache-dir \
    "fastapi>=0.110" \
    "uvicorn[standard]>=0.29" \
    "pydantic>=2.0"

# Copy source (overridden by volume mounts in dev)
COPY server/ ./server/
COPY data/ ./data/

# Run from server/ so relative imports (sim, api) resolve correctly
WORKDIR /app/server

ENV ENTROPY_GARDEN_DB=/data/entropy_garden.db

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
