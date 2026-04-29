# ── Base image ────────────────────────────────────────────────────────────────
# Python 3.11 slim keeps the image small while matching our requires-python.
FROM python:3.11-slim

# ── uv installation ───────────────────────────────────────────────────────────
# Install uv (fast Python package manager) using the official installer script.
# We pin to a specific version for reproducibility.
COPY --from=ghcr.io/astral-sh/uv:0.4.29 /uv /usr/local/bin/uv

WORKDIR /app

# ── Dependencies ──────────────────────────────────────────────────────────────
# Copy dependency files first — Docker caches this layer until they change,
# so rebuilds after code-only edits skip the slow install step.
COPY pyproject.toml requirements.txt ./

# Prefer uv for installs; falls back to pip via requirements.txt.
# --system installs into the system Python (no virtualenv needed in Docker).
# --no-cache keeps the image lean.
RUN uv pip install --system --no-cache -r requirements.txt

# ── Application code ──────────────────────────────────────────────────────────
COPY app.py chain.py guard.py ./

# ── Runtime ───────────────────────────────────────────────────────────────────
# Chainlit listens on 0.0.0.0 so Docker can route traffic to it.
EXPOSE 8000
CMD ["chainlit", "run", "app.py", "--host", "0.0.0.0", "--port", "8000"]
