# NOTE: This Dockerfile requires client/ to be scaffolded first.
# Run: npm create vite@latest client -- --template react-ts
# Then: docker compose --profile client up

FROM node:20-slim

WORKDIR /app

# Install dependencies separately for layer caching
COPY client/package.json client/package-lock.json* ./
RUN npm install

# Copy source (overridden by volume mount in dev)
COPY client/ .

EXPOSE 5173

# --host 0.0.0.0 required for Docker port binding
CMD ["sh", "-c", "npm install && npm run dev -- --host 0.0.0.0"]
