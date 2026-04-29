# 03 — Docker & Containerisation

## Table of Contents

1. [What is Docker?](#1-what-is-docker)
2. [Core Concepts](#2-core-concepts)
3. [Dockerfile Deep Dive](#3-dockerfile-deep-dive)
4. [Docker Compose Deep Dive](#4-docker-compose-deep-dive)
5. [Networking in Docker](#5-networking-in-docker)
6. [Volumes & Data Persistence](#6-volumes--data-persistence)
7. [Essential Docker Commands](#7-essential-docker-commands)
8. [How We Use Docker in This Project](#8-how-we-use-docker-in-this-project)
9. [Common Issues & Debugging](#9-common-issues--debugging)

---

## 1. What is Docker?

### The Problem Docker Solves

Before Docker, deploying software meant:

- "It works on my machine" — different OS, libraries, Python versions between developer, tester, and production
- Complex installation instructions: "Install Python 3.11, then pip install X, make sure you have libpq-dev..."
- Dependency conflicts: project A needs library v1.2, project B needs v2.0 — they can't coexist
- Environment drift: production behaves differently from development over time

### What Docker Does

Docker packages an application and all its dependencies into a **container** — a
self-contained, isolated unit that runs identically anywhere Docker is installed.

```
Without Docker:
  Developer machine  ─── different ───  Test server  ─── different ───  Production
      Python 3.9                           Python 3.11                    Python 3.10
      lib version 1.2                      lib version 1.5                lib version 1.2
      Ubuntu 20                            Ubuntu 22                      Amazon Linux

With Docker:
  Developer machine  ════ identical ════  Test server  ════ identical ════  Production
  [ container: Python 3.11 + lib 1.5 + Ubuntu 22 ]
  [ container: Python 3.11 + lib 1.5 + Ubuntu 22 ]
  [ container: Python 3.11 + lib 1.5 + Ubuntu 22 ]
```

### Docker vs Virtual Machines

Both provide isolation, but differently:

| | Virtual Machine | Docker Container |
|---|---|---|
| What is virtualised | Entire hardware | Just the application layer |
| Includes | Full OS kernel | Shares host OS kernel |
| Size | Gigabytes | Megabytes |
| Start time | Minutes | Seconds |
| Overhead | High | Very low |
| Use case | Strong isolation, different OS | Application packaging |

---

## 2. Core Concepts

### Image

A **Docker image** is a read-only template for creating containers. Think of it as
a snapshot — the filesystem, installed packages, and configuration — frozen at a
point in time.

Images are built from a `Dockerfile`. They are layered — each instruction adds a layer.

```
Image: nlq-chatbot-app
  Layer 5: COPY app.py chain.py guard.py
  Layer 4: RUN uv pip install ...        (installed packages)
  Layer 3: COPY pyproject.toml           
  Layer 2: COPY uv binary
  Layer 1: FROM python:3.11-slim         (base OS + Python)
```

### Container

A **container** is a running instance of an image. You can run many containers from
the same image.

```
Image (blueprint)  →  Container (running instance)
                   →  Container (another instance)
                   →  Container (yet another)
```

When a container stops, its ephemeral filesystem changes are lost. Data that must
survive container restarts must be stored in a **volume**.

### Registry

A **registry** is a service that stores and distributes Docker images. The default
public registry is Docker Hub. Images are referenced as:

```
[registry/]username/image-name[:tag]

python:3.11-slim                           # official Python image from Docker Hub
postgres:16-alpine                         # official PostgreSQL image
ghcr.io/astral-sh/uv:0.4.29               # uv from GitHub Container Registry
```

### Build Context

When you run `docker build`, Docker sends a **build context** — the directory
contents — to the Docker daemon. The `Dockerfile` reads files from this context.

```yaml
# docker-compose.yml
app:
  build:
    context: ./app    # send the ./app directory as build context
                      # Dockerfile inside ./app can only read from ./app
```

---

## 3. Dockerfile Deep Dive

### Our App Dockerfile — Line by Line

```dockerfile
# ── Base image ──────────────────────────────────────────────────────
FROM python:3.11-slim
```

`FROM` sets the starting point. `python:3.11-slim` is an official image from Docker
Hub with Python 3.11 pre-installed. `-slim` is a variant with fewer pre-installed
packages, keeping the image size small.

Every Dockerfile must start with `FROM`.

```dockerfile
# ── uv installation ─────────────────────────────────────────────────
COPY --from=ghcr.io/astral-sh/uv:0.4.29 /uv /usr/local/bin/uv
```

Multi-stage copy — a powerful pattern. Instead of installing uv with a shell command
(which would require curl, downloading scripts, etc.), we **copy the pre-built binary
directly from the official uv Docker image**.

`--from=<image>` says "copy from this image". `/uv` is the source path in that image.
`/usr/local/bin/uv` is the destination in our image. The result: uv is available as
a command with zero installation overhead.

```dockerfile
WORKDIR /app
```

Sets the working directory for subsequent commands. Like `cd /app`.
All relative paths in `COPY`, `RUN`, `CMD` are relative to this.

```dockerfile
# ── Dependencies (cached layer) ─────────────────────────────────────
COPY pyproject.toml requirements.txt ./
RUN uv pip install --system --no-cache -r requirements.txt
```

**Why copy deps before code?**

Docker layer caching: if `pyproject.toml` and `requirements.txt` haven't changed,
Docker reuses the cached `RUN uv pip install` layer. The ~7 second install step
is skipped entirely. Only a change to dependency files forces a reinstall.

`--system` installs into the system Python (no virtualenv — unnecessary in a container).
`--no-cache` skips uv's cache for a leaner image.

```dockerfile
# ── Application code ────────────────────────────────────────────────
COPY app.py chain.py guard.py ./
```

Code is copied after dependencies. This layer changes every time code changes, but
that's just a file copy — nearly instantaneous.

```dockerfile
EXPOSE 8000
CMD ["chainlit", "run", "app.py", "--host", "0.0.0.0", "--port", "8000"]
```

`EXPOSE` documents that the container listens on port 8000 (informational only —
actual port mapping is in `docker-compose.yml`).

`CMD` is the default command to run. `--host 0.0.0.0` is critical — without it,
the server only listens on `localhost` inside the container, unreachable from outside.

### Our Postgres Dockerfile

```dockerfile
FROM postgres:16-alpine
COPY init.sql /docker-entrypoint-initdb.d/init.sql
```

The official PostgreSQL image automatically runs any `.sql` files placed in
`/docker-entrypoint-initdb.d/` on **first startup** (when the data directory is empty).

This is how our schema and seed data gets loaded — no manual steps needed.

### Common Dockerfile Instructions

| Instruction | Purpose | Example |
|---|---|---|
| `FROM` | Base image | `FROM python:3.11-slim` |
| `WORKDIR` | Set working directory | `WORKDIR /app` |
| `COPY` | Copy files into image | `COPY app.py ./` |
| `RUN` | Execute command during build | `RUN pip install flask` |
| `ENV` | Set environment variable | `ENV PORT=8000` |
| `EXPOSE` | Document listened port | `EXPOSE 8000` |
| `CMD` | Default run command | `CMD ["python", "app.py"]` |
| `ENTRYPOINT` | Fixed run command | `ENTRYPOINT ["python"]` |
| `ARG` | Build-time variable | `ARG VERSION=1.0` |

---

## 4. Docker Compose Deep Dive

### What Docker Compose Does

Docker Compose reads a `docker-compose.yml` file and:
- Builds images for services that have a `build:` block
- Creates and starts containers for all services
- Sets up networking between them
- Manages volumes
- Handles startup ordering

One command to start everything: `docker compose up`.

### Our docker-compose.yml — Annotated

```yaml
services:

  # ── Service 1: PostgreSQL ──────────────────────────────────────────
  postgres:
    build:
      context: ./postgres       # Use postgres/Dockerfile
    restart: unless-stopped     # Auto-restart on crash, but not manual stop
    environment:
      POSTGRES_USER:     ${POSTGRES_USER}      # Read from .env file
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB:       ${POSTGRES_DB}
    ports:
      - "5432:5432"             # host:container port mapping
    volumes:
      - postgres_data:/var/lib/postgresql/data  # Named volume for persistence
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s              # Check every 5 seconds
      timeout: 5s               # Fail if no response in 5 seconds
      retries: 10               # Mark unhealthy after 10 failures

  # ── Service 2: Chainlit App ────────────────────────────────────────
  app:
    build:
      context: ./app            # Use app/Dockerfile
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      POSTGRES_HOST:     postgres     # Use Docker service name, not localhost
      POSTGRES_PORT:     5432
      POSTGRES_USER:     ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB:       ${POSTGRES_DB}
      GROQ_API_KEY:      ${GROQ_API_KEY}
      MAX_ROWS:          ${MAX_ROWS:-50}     # Use .env value OR default 50
      GROQ_MODEL:        ${GROQ_MODEL:-llama-3.3-70b-versatile}
    depends_on:
      postgres:
        condition: service_healthy    # Only start after postgres passes healthcheck

volumes:
  postgres_data:    # Declare the named volume (Docker manages it)
```

### The `${VAR:-default}` Pattern

```yaml
MAX_ROWS: ${MAX_ROWS:-50}
```

- If `MAX_ROWS` is set in `.env` → use that value
- If not set → use `50` as the default

This is Docker Compose variable substitution. It gives you sensible defaults while
allowing easy overrides.

### Health Checks

```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U chatbot -d retaildb"]
```

`pg_isready` is a PostgreSQL utility that returns success when the DB is accepting
connections. Docker polls this command and sets the container status to `healthy`
once it passes.

### `depends_on` with `condition: service_healthy`

Without this, Compose starts all services simultaneously. The app container would
try to connect to PostgreSQL before it's ready, fail, and crash.

With `condition: service_healthy`, Docker Compose waits until `pg_isready` succeeds
before starting the app container. Reliable startup every time.

### Restart Policy

```yaml
restart: unless-stopped
```

| Policy | Behaviour |
|---|---|
| `no` | Never restart automatically |
| `always` | Always restart, even on `docker compose stop` |
| `unless-stopped` | Restart on crash, but not when explicitly stopped |
| `on-failure` | Only restart if exit code is non-zero |

`unless-stopped` is the right choice for development — crashes are recovered
automatically, but you retain control with `docker compose stop`.

---

## 5. Networking in Docker

### Default Bridge Network

When Docker Compose starts, it creates a **bridge network** named `<project>_default`.
All services join this network automatically.

```
Host machine
│
└── Docker bridge network: nlq-chatbot_default
    │
    ├── Container: postgres
    │   ├── internal hostname: "postgres"
    │   ├── internal IP: 172.x.x.x (assigned by Docker)
    │   └── port 5432 mapped to host port 5432
    │
    └── Container: app
        ├── internal hostname: "app"
        ├── internal IP: 172.x.x.x (assigned by Docker)
        └── port 8000 mapped to host port 8000
```

Inside the Docker network, containers reach each other by service name.
The `app` container connects to the database at `postgres:5432`, not `localhost:5432`.

### Port Mapping

```yaml
ports:
  - "8000:8000"    # "host_port:container_port"
```

Without port mapping, the container is completely isolated — nothing can reach it
from the host. Port mapping punches a hole through: traffic to `localhost:8000` on
the host is forwarded to port `8000` in the container.

---

## 6. Volumes & Data Persistence

### The Problem

Containers are ephemeral. When a container stops or is removed, any changes to its
filesystem are lost. If PostgreSQL data lived only in the container's filesystem,
every `docker compose down` would wipe the database.

### Named Volumes

A **named volume** is managed by Docker, stored on the host filesystem, and mounted
into the container at a specified path.

```yaml
volumes:
  postgres_data:              # declare the volume

postgres:
  volumes:
    - postgres_data:/var/lib/postgresql/data   # mount into container
```

The data at `/var/lib/postgresql/data` inside the container is actually stored in
Docker's volume store on the host. It persists across:
- Container stops and starts
- Container removals (`docker rm`)
- Image rebuilds

It is only deleted by `docker compose down -v` or `docker volume rm`.

### Bind Mounts (alternative — not used here)

A bind mount maps a specific host directory into the container:

```yaml
volumes:
  - ./my-local-dir:/app/data    # host path : container path
```

Useful for development (edit files on host, see changes immediately in container),
but not ideal for databases (permissions, OS-specific filesystem behaviour).

---

## 7. Essential Docker Commands

### Image Commands

```bash
# List all images
docker images

# Build an image from a Dockerfile in current directory
docker build -t my-image-name .

# Remove an image
docker rmi my-image-name

# Pull an image from a registry
docker pull python:3.11-slim
```

### Container Commands

```bash
# Run a container from an image
docker run -p 8000:8000 my-image-name

# Run in background (detached)
docker run -d -p 8000:8000 my-image-name

# List running containers
docker ps

# List all containers including stopped
docker ps -a

# Stop a container
docker stop <container-id>

# Remove a container
docker rm <container-id>

# Execute a command in a running container
docker exec -it <container-id> bash         # open a shell
docker exec <container-id> psql -U chatbot  # run psql

# View container logs
docker logs <container-id>
docker logs -f <container-id>              # follow (like tail -f)
```

### Docker Compose Commands

```bash
# Start all services (build if needed)
docker compose up

# Start in background
docker compose up -d

# Build and start (force rebuild)
docker compose up --build

# Rebuild and start only one service
docker compose up -d --build app

# Stop all services (containers remain)
docker compose stop

# Stop and remove containers and network
docker compose down

# Stop and remove containers, network, AND volumes
docker compose down -v

# View status
docker compose ps

# View logs for all services
docker compose logs

# View logs for one service, follow
docker compose logs -f app

# Execute command in running service container
docker compose exec postgres psql -U chatbot -d retaildb
docker compose exec app bash
```

### Volume Commands

```bash
# List all volumes
docker volume ls

# Inspect a volume (shows where it's stored on host)
docker volume inspect nlq-chatbot_postgres_data

# Remove a specific volume
docker volume rm nlq-chatbot_postgres_data

# Remove all unused volumes
docker volume prune
```

---

## 8. How We Use Docker in This Project

### Build Process

```bash
docker compose up --build
```

1. Docker reads `docker-compose.yml`
2. Builds `nlq-chatbot-postgres` from `postgres/Dockerfile`
   - Starts with `postgres:16-alpine`
   - Copies `init.sql` into init directory
3. Builds `nlq-chatbot-app` from `app/Dockerfile`
   - Starts with `python:3.11-slim`
   - Copies `uv` binary from its image
   - Copies and installs all dependencies (cached if unchanged)
   - Copies application code
4. Creates the `nlq-chatbot_default` network
5. Starts `postgres` container
6. Polls `pg_isready` until healthy
7. Starts `app` container
8. Both containers running, accessible on host ports

### Day-to-Day Development

**Code change only (most common):**
```bash
docker compose up -d --build app
# Only rebuilds app image — Layer 5 (code copy) invalidated
# Dependency layers are cached → ~2 second rebuild
```

**Dependency change:**
```bash
# Update requirements.txt then:
docker compose up -d --build app
# Layers 3-5 invalidated → ~7 second rebuild
```

**Database schema change:**
```bash
docker compose down -v          # delete volume so init.sql re-runs
docker compose up --build       # full rebuild
```

---

## 9. Common Issues & Debugging

### "Port already in use"

```
Error: Bind for 0.0.0.0:5432 failed: port is already allocated
```

Another process (or Docker container) is using port 5432. Solutions:
```bash
# Find what's using the port
lsof -i :5432

# Or change the host port in docker-compose.yml
ports:
  - "5433:5432"   # map to 5433 on host instead
```

### Container exits immediately

```bash
docker compose logs app    # check logs for the error
```

Common causes: missing env var, code syntax error, failed to connect to DB.

### "Database not initialised" / Tables missing

The init script only runs when the PostgreSQL data directory is empty. If you've
started the container before (even if it failed), the volume exists and init.sql
won't re-run.

```bash
docker compose down -v    # delete the volume
docker compose up --build # fresh start
```

### App can't connect to database

Check:
1. Is `POSTGRES_HOST=postgres` (the service name, not `localhost`)?
2. Is the postgres container healthy? (`docker compose ps`)
3. Are the credentials in `.env` correct?

```bash
# Test DB connection manually
docker compose exec postgres psql -U chatbot -d retaildb -c "SELECT 1;"
```

### Changes to code not reflected

Make sure you're rebuilding:
```bash
docker compose up -d --build app
```

Just `docker compose up -d` reuses the existing image without rebuilding.
