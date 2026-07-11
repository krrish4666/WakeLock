# 🚀 WakeLock Production Deployment Guide

Transform your local WakeLock application into a 24/7/365 production-grade cloud service accessible by thousands of Telegram users worldwide.

---

## 1. Cloud Infrastructure & Service Requirements

To run WakeLock in production without needing your personal laptop powered on, you need three cloud building blocks:

### A. Cloud PostgreSQL Database (Persistent Storage)
* **Recommended Service**: [Neon Postgres](https://neon.tech) (Free Tier available, serverless auto-scaling) or **Supabase** / **Railway Postgres**.
* **Why PostgreSQL over SQLite?**  
  In production with multi-concurrency and multiple Celery background workers running simultaneously, SQLite will encounter database lock (`database is locked`) contention. PostgreSQL handles thousands of concurrent async transactions (`asyncpg`) without locking up.
* **Format for `.env` (`DATABASE_URL`)**:  
  Your cloud provider will give you a standard Postgres connection string like `postgres://user:password@ep-xyz.region.aws.neon.tech/dbname?sslmode=require`.  
  **IMPORTANT**: Because WakeLock uses asynchronous SQLAlchemy (`AsyncEngine`), you **must** replace `postgres://` or `postgresql://` with `postgresql+asyncpg://` in your connection string:
  ```env
  DATABASE_URL=postgresql+asyncpg://user:password@ep-xyz.region.aws.neon.tech/dbname?ssl=require
  ```

### B. Cloud Redis Instance (Celery Broker & OTP Pipeline)
* **Recommended Service**: [Upstash Redis](https://upstash.com) (Serverless, free tier available) or **Railway Redis** / **Redis Cloud**.
* **Why Redis?**  
  Redis powers two critical mechanisms:
  1. Ephemeral 2-minute OTP token storage and single-use invalidation (`wakelock:otp:{id}`).
  2. Celery message broker enabling instant communication between the `beat` scheduler (`process_due_alarms`) and `worker` execution units (`drop_random_otp`).
* **Format for `.env` (`REDIS_URL`)**:
  ```env
  # If using standard Redis / Railway:
  REDIS_URL=redis://default:password@redis-xxxxx.c1.region.provider.com:6379/0

  # If using Upstash or SSL/TLS protected Redis (note the double 's' in rediss://):
  REDIS_URL=rediss://default:password@xxxxxx.upstash.io:6379?ssl_cert_reqs=none
  ```

---

## 2. Option A: Easiest Cloud PaaS Deployment (Railway / Render)

If you don't want to manage Linux server configurations or Docker setup manually, using a **Platform-as-a-Service (PaaS)** like [Railway.app](https://railway.app) or [Render.com](https://render.com) is the fastest approach.

### Step-by-Step Railway Deployment:
1. **Push your code to GitHub**: Commit your current master branch to a private GitHub repository.
2. **Create a Railway Project**:
   * Log into Railway -> **New Project** -> **Deploy from GitHub repo** -> Select your `wakelock` repo.
3. **Provision Managed PostgreSQL & Redis**:
   * Click **+ New** inside your Railway canvas -> **Database** -> **Add PostgreSQL**.
   * Click **+ New** inside your Railway canvas -> **Database** -> **Add Redis**.
4. **Configure Environment Variables in Railway (`Variables` tab)**:
   * `TELEGRAM_BOT_TOKEN`: `8248929879:AAFW3UnAL66TkY6RlI7VYteF_DtlZPXrRbw` (or your production bot token)
   * `SECRET_KEY`: Generate a secure 64-character random hex string.
   * `DATABASE_URL`: `${Postgres.DATABASE_URL}` *(Remember to change `postgresql://` to `postgresql+asyncpg://` in the custom variable string)*
   * `REDIS_URL`: `${Redis.REDIS_URL}`
5. **Scale to 3 Services from the Same Repository**:
   Because WakeLock requires 3 distinct operating processes (`Web API/Bot`, `Celery Worker`, `Celery Beat`), inside your Railway canvas right-click your GitHub repo card and click **Duplicate** twice so you have 3 identical cards pointing to the same codebase:
   * **Card 1 (`wakelock-api`)**: Go to **Settings** -> **Start Command** -> Enter:
     ```bash
     python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
     ```
   * **Card 2 (`wakelock-worker`)**: Go to **Settings** -> **Start Command** -> Enter:
     ```bash
     python -m celery -A app.worker.celery_app worker --loglevel=info -P threads
     ```
   * **Card 3 (`wakelock-beat`)**: Go to **Settings** -> **Start Command** -> Enter:
     ```bash
     python -m celery -A app.worker.celery_app beat --loglevel=info
     ```

---

## 3. Option B: Self-Hosted Docker Compose Deployment (DigitalOcean / AWS VPS)

If you have a Linux VPS (e.g., DigitalOcean Droplet, AWS EC2, or Hetzner Cloud), we have already created `Dockerfile` and `docker-compose.yml` in your repository root for 1-click containerized deployment.

### Step-by-Step VPS Deployment:
1. **SSH into your VPS and clone the repository**:
   ```bash
   git clone https://github.com/yourusername/wakelock.git
   cd wakelock
   ```
2. **Create your production `.env` file**:
   ```bash
   nano .env
   ```
   Paste your configuration:
   ```env
   PROJECT_NAME="WakeLock Production Engine"
   SECRET_KEY="your_secure_production_secret_key"
   DATABASE_URL="postgresql+asyncpg://user:password@neon-cloud-host:5432/dbname?ssl=require"
   REDIS_URL="redis://redis:6379/0" # Points to the local Docker Redis container, or your cloud Upstash URL
   TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
   ```
3. **Launch the complete 4-container stack in detached background mode**:
   ```bash
   docker compose up -d --build
   ```
4. **Verify container logs and status**:
   ```bash
   # Check if all 4 services (api, worker, beat, redis) are running cleanly
   docker compose ps

   # Watch real-time logs of the alarm drop worker
   docker compose logs -f worker
   ```

---

## 4. Database Migrations & Initial Setup (`Alembic`)

Before the bot can accept its first `/start` command in production, the PostgreSQL tables must be created.

### Running Alembic Migrations:
If you are using **Railway / PaaS**, open the Railway Terminal tab on `wakelock-api` and run:
```bash
python -m alembic upgrade head
```

If you are using **Docker Compose / VPS**, execute inside the running API container:
```bash
docker compose exec api python -m alembic upgrade head
```

*(Note: Because our `app/core/database.py` and models inherit from `Base.metadata.create_all` during setup or tests, your tables (`users`, `user_preferences`, `accountability_plans`, `wake_sessions`, `otp_tokens`, `wallets`, `wallet_transactions`, `platform_revenue`) will be automatically created in PostgreSQL seamlessly on first connection!)*

---

## 5. Production Checklist & Architectural Best Practices

* [ ] **Use Long-Polling vs Webhook**:  
  By default, our `app/main.py` lifespan executes `application.updater.start_polling()`, meaning your bot actively connects to Telegram's servers outbound. This requires **zero firewall port forwarding or public domain SSL configuration** on Telegram's end! It works out of the box anywhere.
* [ ] **Set Timezone Accurately**:  
  Ensure your Celery configuration (`app/worker.py`) retains `timezone="Asia/Kolkata"` (or your target user demographic timezone) so daily 00:05 AM completion crons and exact morning alarms (`HH:MM`) match user local clocks precisely.
* [ ] **Monitor Worker Memory (`-P threads` vs `prefork`)**:  
  In cloud Linux containers (`Dockerfile`), Celery runs best with `-P threads` or standard `prefork` pool. We configured `-P threads` in `docker-compose.yml` for maximum efficiency on lightweight 512MB/1GB cloud instances.
* [ ] **Security (`SECRET_KEY`)**:  
  Never reuse `supersecretkeythatyoushouldchange` in production. Always generate a fresh cryptographic key (`python -c "import secrets; print(secrets.token_hex(32))"`).
