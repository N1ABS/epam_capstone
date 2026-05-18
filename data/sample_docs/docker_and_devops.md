# Docker and DevOps — Personal Reference

## Docker Essentials

### Key Concepts

| Concept | Description |
|---|---|
| **Image** | Read-only template built from a Dockerfile |
| **Container** | Running instance of an image |
| **Volume** | Persistent storage mounted into a container |
| **Network** | Virtual network connecting containers |
| **Registry** | Repository for images (Docker Hub, GHCR) |

### Dockerfile Best Practices

```dockerfile
# Pin the base image tag — never use :latest in production
FROM python:3.11-slim

# Create a non-root user for security
RUN useradd --create-home appuser
WORKDIR /app

# Copy dependency files first to exploit layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY ui/ ./ui/

USER appuser
EXPOSE 8501
CMD ["streamlit", "run", "ui/app.py", "--server.address=0.0.0.0"]
```

**Layer caching tip:** copy `requirements.txt` and install dependencies before
copying source code. Dependencies change less often than code, so the expensive
`pip install` layer is cached on code-only changes.

### Docker Compose

Use Compose for local multi-service development:

```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6333:6333"]
    volumes: [qdrant_storage:/qdrant/storage]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/health"]
      interval: 10s
      retries: 5

  app:
    build: .
    ports: ["8501:8501"]
    env_file: .env
    depends_on:
      qdrant:
        condition: service_healthy
```

Key `depends_on` options:
- `condition: service_started` — container started (default).
- `condition: service_healthy` — healthcheck passed (preferred for DBs).

---

## Useful Docker Commands

```bash
# Build and tag
docker build -t myapp:1.0 .

# Run interactively
docker run -it --rm -p 8501:8501 --env-file .env myapp:1.0

# Inspect a running container
docker exec -it <container_id> bash

# Follow logs
docker logs -f <container_id>

# Remove stopped containers and dangling images
docker system prune -f

# Compose shortcuts
docker compose up -d         # start services in background
docker compose down -v       # stop and remove volumes
docker compose logs -f app   # follow app logs
```

---

## CI/CD with GitHub Actions

Minimal Python CI workflow:

```yaml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.11"}
      - run: pip install -r requirements.txt
      - run: pytest tests/ -v --tb=short
```

**Best practices:**
- Cache pip dependencies with `actions/cache` to shorten run time.
- Run linting (`ruff check .`) and type checking (`mypy src/`) in parallel jobs.
- Use environment secrets (`${{ secrets.OPENAI_API_KEY }}`) — never hard-code keys.
- Separate `test` and `deploy` jobs; only deploy on `main` branch after tests pass.

---

## Environment and Secrets Management

**Local development:**
- `.env` file loaded by `python-dotenv`; always gitignored.
- `.env.example` committed with placeholder values as documentation.

**Production:**
- Use the hosting platform's secret manager (GitHub Secrets, AWS SSM, GCP Secret
  Manager) — never store secrets in environment variables baked into Docker images.
- Rotate API keys regularly; treat leaked keys as compromised immediately.

**Validation on startup:**
```python
import os, sys

required = ["OPENAI_API_KEY", "TAVILY_API_KEY"]
missing = [k for k in required if not os.getenv(k)]
if missing:
    sys.exit(f"Missing required environment variables: {missing}")
```

---

## Observability in Production

**Structured logging** (JSON format for log aggregation tools):
```python
import logging, json

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        })
```

**Health endpoints:** expose `/health` for load balancers and Kubernetes probes.

**Metrics to monitor:**
- Request rate and error rate (RED: Rate, Errors, Duration).
- Vector DB query latency (p50, p95, p99).
- LLM token usage and cost (track via LangSmith or custom spans).
- Container memory and CPU (Docker stats or cAdvisor).

---

## Production Deployment Checklist

- [ ] Non-root Docker user
- [ ] Pinned image tags (no `:latest`)
- [ ] Secrets from environment / secret manager, not image layers
- [ ] Health check defined in Compose / Kubernetes
- [ ] Graceful shutdown handler (`SIGTERM`)
- [ ] Resource limits set (`mem_limit`, CPU quota)
- [ ] Log aggregation configured (stdout → Loki / CloudWatch)
- [ ] Monitoring and alerting configured (uptime, error rate)
