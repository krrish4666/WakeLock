# WakeLock — Production Deployment Requirements & Code Changes Guide

> **Goal**: Transform the current SQLite + local Redis development setup into a real 24/7 Telegram bot that anyone can use — with cloud PostgreSQL (Neon), managed Redis (Upstash), proper secrets, container orchestration, and production-hardened code.

---

## Table of Contents

1. [Infrastructure Requirements](#1-infrastructure-requirements)
2. [Environment & Secrets](#2-environment--secrets)
3. [Database: SQLite → Cloud PostgreSQL (Neon)](#3-database-sqlite--cloud-postgresql-neon)
4. [Redis: Local → Managed (Upstash/Redis Cloud)](#4-redis-local--managed-upstashredis-cloud)
5. [Docker & Containerization Changes](#5-docker--containerization-changes)
6. [Celery Worker Production Tuning](#6-celery-worker-production-tuning)
7. [Bot: Polling → Webhook Mode (Recommended)](#7-bot-polling--webhook-mode-recommended)
8. [Alembic Migrations for Production](#8-alembic-migrations-for-production)
9. [Security Hardening](#9-security-hardening)
10. [Monitoring, Logging & Health Checks](#10-monitoring-logging--health-checks)
11. [Deployment Step-by-Step](#11-deployment-step-by-step)
12. [Verification Checklist](#12-verification-checklist)
13. [Architecture Diagram (Production)](#13-architecture-diagram-production)

---

## 1. Infrastructure Requirements

| Service | Dev (Current) | Production (Required) |
|---------|---------------|----------------------|
| **Database** | SQLite (`wakelock.db`) | PostgreSQL via [Neon](https://neon.tech) (serverless) or Supabase / AWS RDS |
| **Redis** | `redis://localhost:6379/0` | Managed Redis via [Upstash](https://upstash.com) (serverless) or Redis Cloud / Railway Redis |
| **Bot Token** | Dev token in `.env` | Real token from [@BotFather](https://t.me/BotFather) on Telegram |
| **Secrets** | `supersecretkeythatyoushouldchange` | Cryptographically generated secret |
| **Hosting** | Local machine | Docker VPS (DigitalOcean/AWS) or PaaS (Railway/Render) |
| **File Storage** | Local `wakelock.db` file | N/A (all state in PostgreSQL + Redis) |

---

## 2. Environment & Secrets

### Current `.env` (Dev)
```env
DATABASE_URL=sqlite+aiosqlite:///./wakelock.db
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=supersecretkeythatyoushouldchange
TELEGRAM_BOT_TOKEN=8248929879:AAFW3UnAL66TkY6RlI7VYteF_DtlZPXrRbw
```

### Production `.env`
```env
PROJECT_NAME="WakeLock Production Engine"
SECRET_KEY="<generate: python -c 'import secrets; print(secrets.token_hex(32))'>"
DATABASE_URL="postgresql+asyncpg://user:password@ep-xxx.us-east-2.aws.neon.tech/wakelock?sslmode=require"
REDIS_URL="rediss://default:password@xxxx.upstash.io:6379"
TELEGRAM_BOT_TOKEN="<real token from @BotFather>"
```

### Code Changes Required

#### `app/core/config.py` (no change needed — already reads from env)
```python
class Settings(BaseSettings):
    SECRET_KEY: str = "supersecretkeythatyoushouldchange"  # overridden by .env
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/wakelock"  # overridden by .env
    REDIS_URL: str = "redis://localhost:6379/0"  # overridden by .env
    TELEGRAM_BOT_TOKEN: str = "your_telegram_bot_token_here"  # overridden by .env
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)
```

**Status**: No code change needed. All values are overridden by `.env` at runtime via `pydantic-settings`.

---

## 3. Database: SQLite → Cloud PostgreSQL (Neon)

### Why This Change Is Required

| Issue | SQLite (Dev) | PostgreSQL (Prod) |
|-------|-------------|-------------------|
| Concurrent writes | `database is locked` errors | MVCC handles 1000s of concurrent writes |
| Celery workers | 3 processes contend for 1 file | Connection pooling via `asyncpg` |
| Scalability | Single-file bottleneck | Serverless auto-scale |
| Uptime | File corruption risk | Managed backups, point-in-time recovery |

### Code Changes Required

#### `app/core/database.py` (verify — should work as-is)
```python
engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
```
**Status**: No change needed. The engine is configured from `settings.DATABASE_URL` which will point to PostgreSQL in production.

#### `app/core/config.py` (default already PostgreSQL)
```python
DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/wakelock"
```
**Status**: No change needed. Default is already asyncpg. Dev overrides with `sqlite+aiosqlite:///` in `.env`.

#### `app/core/database.py` — Add connection pooling limits for production
**Change required**: Add pool size and overflow limits to prevent connection exhaustion under load.

```python
# Production: add pool settings
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_size=5,            # NEW: base pool connections
    max_overflow=10,         # NEW: max extra connections beyond pool_size
    pool_pre_ping=True       # NEW: verify connections before use
)
```

#### Alembic `env.py` (already reads settings.DATABASE_URL — no change needed)
```python
configuration["sqlalchemy.url"] = settings.DATABASE_URL
```
**Status**: No change needed. Alembic dynamically reads the URL from settings.

#### `alembic.ini` — Placeholder URL (informational only)
```
sqlalchemy.url = driver://user:pass@localhost/dbname
```
**Status**: No change needed. `env.py` overrides this at runtime.

---

## 4. Redis: Local → Managed (Upstash/Redis Cloud)

### Why This Change Is Required

| Concern | Local Redis | Managed Redis |
|---------|-------------|---------------|
| 24/7 availability | Requires local machine on | Geo-replicated, SLA-backed |
| OTP storage | In-memory, lost on restart | Persisted, TTL-managed |
| Celery broker | Single point of failure | Clustered, failover |
| Scalability | Fixed memory | Auto-scaling tiers |

### Code Changes Required

#### `app/services/otp.py` — Handle SSL/TLS Redis connections
**Change required**: When using `rediss://` (Upstash, Redis Cloud with TLS), the connection needs `ssl_cert_reqs` handling. The current code creates a fresh connection each call which is inefficient and may fail with SSL.

```python
# Current (creates new connection per call):
async with Redis.from_url(settings.REDIS_URL, decode_responses=True) as client:
    ...

# Production fix — create a persistent connection pool at module level:
from redis.asyncio import Redis as AsyncRedis
import ssl

# Add to app/core/redis.py (NEW FILE):
redis_client: AsyncRedis | None = None

def get_redis() -> AsyncRedis:
    global redis_client
    if redis_client is None:
        redis_client = AsyncRedis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
            ssl_cert_reqs=ssl.CERT_NONE if settings.REDIS_URL.startswith("rediss://") else None
        )
    return redis_client
```

Then update `app/services/otp.py` to use the shared connection instead of creating a new one per call.

---

## 5. Docker & Containerization Changes

### Current `Dockerfile`

| Aspect | Current | Production Requirement |
|--------|---------|----------------------|
| User | `root` | Non-root user for security |
| Health check | None | Add `HEALTHCHECK` |
| Entrypoint | Hardcoded `uvicorn` | Flexible for worker/beat too |
| Build deps | Kept in final image | Multi-stage to reduce size |

### Changes Required

#### `Dockerfile` — Add non-root user, HEALTHCHECK, multi-entry support

```dockerfile
FROM python:3.12-slim AS builder

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip wheel setuptools && \
    pip install --no-cache-dir -r requirements.txt

# ---- Production stage ----
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev && \
    rm -rf /var/lib/apt/lists/* && \
    addgroup --system --gid 1001 wakelock && \
    adduser --system --uid 1001 --ingroup wakelock --no-create-home wakelock

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY . .

RUN chown -R wakelock:wakelock /app

USER wakelock

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["python", "-m"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### `docker-compose.yml` — Add health checks, DB readiness dependency

```yaml
version: '3.8'

services:
  api:
    build: .
    command: python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
    env_file: .env
    ports:
      - "8000:8000"
    depends_on:
      redis:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s

  worker:
    build: .
    command: python -m celery -A app.worker.celery_app worker --loglevel=info -P threads --concurrency=4
    env_file: .env
    depends_on:
      api:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped

  beat:
    build: .
    command: python -m celery -A app.worker.celery_app beat --loglevel=info --pidfile=/tmp/celerybeat.pid
    env_file: .env
    depends_on:
      api:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3
    volumes:
      - redis_data:/data

volumes:
  redis_data:
```

**Key changes**:
- `restart: always` → `restart: unless-stopped`
- Added `healthcheck` to all services
- Added `depends_on` with `condition: service_healthy`
- Added `--concurrency=4` to worker (tunable)
- Added `--pidfile` to beat to prevent stale PID issues
- Added Redis volume for persistence
- Removed `depends_on: - api` from worker/beat (circular dependency risk — use healthchecks instead)

---

## 6. Celery Worker Production Tuning

### Current `app/worker.py`

```python
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    beat_schedule={...}
)
```

### Changes Required

#### `app/worker.py` — Add rate limits, retry policies, task rejection

```python
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_acks_late=True,             # NEW: re-queue task if worker crashes mid-execution
    task_reject_on_worker_lost=True, # NEW: reject if worker dies
    worker_max_tasks_per_child=200,  # NEW: restart worker after 200 tasks (memory leak guard)
    worker_prefetch_multiplier=1,    # NEW: only prefetch 1 task at a time (fair distribution)
    task_soft_time_limit=300,        # NEW: 5 min soft limit per task
    task_time_limit=600,             # NEW: 10 min hard limit per task
    beat_schedule={
        "check-alarms-every-minute": {
            "task": "app.tasks.plan_tasks.process_due_alarms",
            "schedule": crontab(minute="*"),
            "options": {"expires": 30}  # NEW: drop stale alarm checks after 30s
        },
        "check-completed-plans-daily": {
            "task": "app.tasks.plan_tasks.check_completed_plans",
            "schedule": crontab(hour="0", minute="5"),
            "options": {"expires": 300}  # NEW: drop stale completions after 5 min
        }
    }
)
```

#### `app/tasks/plan_tasks.py` — Add error handling and logging

The current tasks catch exceptions silently in `send_alert`. Add proper error logging:

```python
import logging
logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_due_alarms(self):
    try:
        asyncio.run(_process_due_alarms_async())
    except Exception as exc:
        logger.exception("process_due_alarms failed")
        raise self.retry(exc=exc)

@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def drop_random_otp(self, attendance_id, user_id):
    try:
        asyncio.run(_drop_random_otp_async(attendance_id, user_id))
    except Exception as exc:
        logger.exception("drop_random_otp failed for session %s", attendance_id)
        raise self.retry(exc=exc)
```

---

## 7. Bot: Polling → Webhook Mode (Recommended)

### Why Switch

| Mode | Advantage | Disadvantage |
|------|-----------|-------------|
| **Polling** (current) | Works behind NAT/firewall, no domain needed | Higher latency, extra load, less reliable |
| **Webhook** | Real-time, lower latency, Telegram retries on failure | Requires public HTTPS URL + SSL cert |

### Changes Required

#### `app/main.py` — Replace polling with webhook

```python
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from app.core.config import settings
from app.bot import application

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{settings.WEBHOOK_BASE_URL}{WEBHOOK_PATH}"

@asynccontextmanager
async def lifespan(app: FastAPI):
    await application.initialize()
    await application.start()
    # Set webhook (instead of start_polling)
    await application.bot.set_webhook(url=WEBHOOK_URL)
    yield
    await application.stop()
    await application.shutdown()

app = FastAPI(title=settings.PROJECT_NAME, version="4.0", lifespan=lifespan)

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

@app.get("/")
async def root():
    return {"message": "WakeLock API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

#### `app/core/config.py` — Add webhook URL setting

```python
class Settings(BaseSettings):
    ...
    WEBHOOK_BASE_URL: str = "https://your-domain.com"  # NEW
```

#### Production `.env` addition
```env
WEBHOOK_BASE_URL=https://wakelock.yourdomain.com
```

**Alternative**: If a public domain + HTTPS is not feasible, **keep long-polling** but add a process supervisor (e.g., supervisord or the Docker restart policy) to restart the bot on failure.

---

## 8. Alembic Migrations for Production

### Current Setup

- `alembic.ini` has hardcoded placeholder URL (overridden by `env.py`)
- `env.py` reads `settings.DATABASE_URL` from `app.core.config`
- 3 existing migrations in `backend_migrations/versions/`
- Migrations created with `render_as_batch=True` (SQLite compatibility)

### Changes Required

#### `backend_migrations/env.py` — Remove `render_as_batch=True` for PostgreSQL

```python
# PostgreSQL does not need batch mode — it can cause issues
context.configure(
    connection=connection,
    target_metadata=target_metadata
    # render_as_batch=True   # REMOVE for PostgreSQL
)
```

**Why**: `render_as_batch=True` is a SQLite workaround. PostgreSQL supports ALTER TABLE natively. Keeping batch mode may generate incorrect ALTER statements.

#### Migration Execution Strategy

Auto-run migrations on container startup by adding a script:

**NEW FILE: `scripts/run_migrations.sh`** (or embed in Dockerfile ENTRYPOINT)

```bash
#!/bin/bash
echo "Running Alembic migrations..."
python -m alembic upgrade head
echo "Migrations complete. Starting application..."
exec "$@"
```

Or use a Python script:

**NEW FILE: `app/prestart.py`**
```python
import asyncio
from alembic.config import Config
from alembic import command

def run_migrations():
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")

if __name__ == "__main__":
    run_migrations()
```

---

## 9. Security Hardening

### Checklist of Required Changes

| Issue | Current | Fix Required |
|-------|---------|-------------|
| **Secret key** | `supersecretkeythatyoushouldchange` | Generate with `secrets.token_hex(32)` |
| **Bot token in code** | Hardcoded default in `config.py` | Already env-based — ensure `.env` is never committed |
| **OTP rate limiting** | None | Add counter per user per session |
| **DB connection strings** | Plaintext in `.env` | Restrict file permissions (`chmod 600`) |
| **Error exposure** | Bare `except` clauses mask all errors | Log exceptions properly |
| **Redis auth** | None (localhost) | TLS + password for managed Redis |
| **Celery serialization** | JSON (safe) | Already safe — keep as-is |

### Code Changes

#### `app/services/verification.py` — Add OTP rate limiting

```python
from datetime import datetime, timedelta
from collections import defaultdict

# In-memory rate limiter (for single worker; use Redis for multi-worker)
otp_attempts: dict[int, list[datetime]] = defaultdict(list)
MAX_OTP_ATTEMPTS = 5
OTP_WINDOW_SECONDS = 300  # 5 minutes

@staticmethod
async def verify_user_otp(db, telegram_id, otp_code):
    # Rate limit check
    now = datetime.now()
    attempts = otp_attempts[telegram_id]
    attempts[:] = [t for t in attempts if t > now - timedelta(seconds=OTP_WINDOW_SECONDS)]
    if len(attempts) >= MAX_OTP_ATTEMPTS:
        return "[ERROR] Too many failed attempts. Please wait 5 minutes."
    attempts.append(now)
    # ... rest of verification logic
```

**Better approach**: Store rate limit counters in Redis to work across all workers.

---

## 10. Monitoring, Logging & Health Checks

### Current State

- Only a basic `/health` endpoint that returns `{"status": "healthy"}`
- No actual DB/Redis connectivity check
- No structured logging
- Exception handling uses bare `print()` or `pass`

### Changes Required

#### `app/main.py` — Improve health check

```python
@app.get("/health")
async def health_check():
    health = {"status": "healthy", "checks": {}}
    
    # Check DB connectivity
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(select(1))
        health["checks"]["database"] = "ok"
    except Exception as e:
        health["checks"]["database"] = f"error: {e}"
        health["status"] = "degraded"
    
    # Check Redis connectivity
    try:
        redis_client = get_redis()
        await redis_client.ping()
        health["checks"]["redis"] = "ok"
    except Exception as e:
        health["checks"]["redis"] = f"error: {e}"
        health["status"] = "degraded"
    
    return health
```

#### Add structured logging

**NEW FILE: `app/core/logging.py`**
```python
import logging
import sys

def setup_logging():
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Quiet down noisy libs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
```

Call `setup_logging()` at the top of `app/main.py`.

---

## 11. Deployment Step-by-Step

### A. Provision Cloud Services

1. **Create a Telegram Bot** via [@BotFather](https://t.me/BotFather)
   - `/newbot` → name: `WakeLockBot` → username: `@YourWakeLockBot`
   - Save the bot token

2. **Create a Neon PostgreSQL Database**
   - Sign up at [neon.tech](https://neon.tech)
   - Create a project → copy connection string
   - Transform: `postgresql://user:pass@host/db` → `postgresql+asyncpg://user:pass@host/db?sslmode=require`

3. **Create an Upstash Redis Instance**
   - Sign up at [upstash.com](https://upstash.com)
   - Create a Redis database → copy `REDIS_URL` (note `rediss://` with SSL)

4. **Generate secrets**
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

### B. Option 1: Deploy on Railway.app (PaaS — Easiest)

1. Push code to GitHub
2. Railway → New Project → Deploy from GitHub
3. Add PostgreSQL and Redis plugins
4. Set env vars in Railway dashboard (as shown in Section 2)
5. Duplicate service into 3 Railway services:
   - **api**: `python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **worker**: `python -m celery -A app.worker.celery_app worker --loglevel=info -P threads`
   - **beat**: `python -m celery -A app.worker.celery_app beat --loglevel=info`
6. Run migrations via Railway Terminal:
   ```bash
   python -m alembic upgrade head
   ```

### C. Option 2: Deploy on VPS with Docker Compose

1. Provision a VPS (DigitalOcean $12/mo droplet, or similar)
2. Install Docker + Docker Compose
3. Clone repo, create `.env` with production values
4. Build & start:
   ```bash
   docker compose up -d --build
   ```
5. Run migrations:
   ```bash
   docker compose exec api python -m alembic upgrade head
   ```
6. Check logs:
   ```bash
   docker compose logs -f api worker beat
   ```

### D. Option 3: Deploy on Render / Fly.io

Similar to Railway — create 3 services (web worker, celery worker, celery beat) from the same repo with different start commands.

---

## 12. Verification Checklist

After deployment, verify each component:

- [ ] **Health endpoint**: `GET /health` returns `{"status": "healthy"}`
- [ ] **Database**: Tables exist (`users`, `wallets`, `accountability_plans`, `wake_sessions`, `otp_tokens`, `wallet_transactions`, `user_preferences`, `platform_revenue`)
- [ ] **Redis**: `redis-cli ping` returns `PONG` (or via Upstash CLI)
- [ ] **Bot responds**: Send `/start` to your bot on Telegram
- [ ] **Plan creation**: `/plan 100 7` works (with sufficient balance after `/deposit 500`)
- [ ] **Alarm scheduling**: `/alarm 05:00` + `/buffer 10` saves to DB
- [ ] **Celery Beat**: `docker compose logs beat` shows heartbeat
- [ ] **Celery Worker**: `docker compose logs worker` shows task execution
- [ ] **OTP flow**: At alarm time, bot sends wakeup message → OTP drop → verification works
- [ ] **Penalties**: Failing to respond deducts penalty from locked balance
- [ ] **Plan completion**: Plans auto-complete and release funds at end_date
- [ ] **Migrations**: All 3 Alembic revisions applied (check `alembic_version` table)
- [ ] **No secrets in code**: `.env` not in git, no hardcoded tokens

---

## 13. Architecture Diagram (Production)

```
                          Telegram Users
                               |
                               | HTTPS Webhook / Long-Polling
                               v
                     +-----------------+
                     |  FastAPI Server  |  (Port 8000)
                     |  (app/main.py)   |
                     |  + Bot Polling   |
                     +--------+--------+
                              |
              +---------------+---------------+
              |                               |
      +-------v-------+             +---------v--------+
      |  Celery Beat   |             |  Celery Worker   |
      |  (Scheduler)   |             |  (Executor)      |
      |  every 1 min   |             |  -P threads      |
      |  every day     |             |  concurrency=4   |
      +-------+-------+             +---------+--------+
              |                               |
              +----------+--------------------+
                         |
                  +------v------+
                  |    Redis     |  ← Upstash / Docker Redis
                  |  (Broker +   |
                  |   OTP Cache) |
                  +------+------+
                         |
                  +------v------+
                  |  PostgreSQL  |  ← Neon / Cloud
                  |  (All State) |
                  +-------------+
```

---

## Summary of All Files Requiring Changes

| File | Change Category | Description |
|------|----------------|-------------|
| `app/core/database.py` | **Production hardening** | Add `pool_size`, `max_overflow`, `pool_pre_ping` |
| `app/core/config.py` | **New setting** | Add `WEBHOOK_BASE_URL` if using webhook mode |
| `app/core/redis.py` | **NEW FILE** | Shared Redis connection pool manager |
| `app/core/logging.py` | **NEW FILE** | Structured logging setup |
| `app/services/otp.py` | **Refactor** | Use shared Redis pool instead of per-call connections |
| `app/services/verification.py` | **Security** | Add OTP rate limiting (in-memory or Redis-based) |
| `app/main.py` | **Configurable** | Webhook mode (alternative to polling) |
| `app/worker.py` | **Production tuning** | Add retry policies, time limits, task acks |
| `app/tasks/plan_tasks.py` | **Resilience** | Add retry decorators, proper logging |
| `app/prestart.py` | **NEW FILE** | Auto-run Alembic migrations on startup |
| `Dockerfile` | **Security + health** | Multi-stage build, non-root user, HEALTHCHECK |
| `docker-compose.yml` | **Resilience** | Health checks, depends_on conditions, volumes |
| `backend_migrations/env.py` | **Compatibility** | Remove `render_as_batch=True` for PostgreSQL |
| `.env` (not committed) | **Secrets** | Replace all values with production credentials |
