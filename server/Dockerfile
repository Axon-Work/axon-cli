FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml .

# Install dependencies
RUN uv pip install --system --no-cache -r pyproject.toml

# Copy application
COPY axon_server/ axon_server/

EXPOSE 8000

CMD ["uvicorn", "axon_server.main:app", "--host", "0.0.0.0", "--port", "8000"]
