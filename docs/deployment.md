# V1 Deployment

This document covers a clean deployment on a host with Docker Desktop, Docker Compose v2, and Git. Compose includes PostgreSQL 16 and Redis 7. Keep `.env` outside source control.

## 1. Prepare

Run `git clone <repository-url>`, enter the repository directory, and run `Copy-Item .env.example .env` on PowerShell (or `cp .env.example .env` on Linux). Edit `.env` before starting.

The free Chinese primary feed requires `ENABLE_CRAWLER=true` and `ENABLE_CHINANEWS=true`; its default URL is the official China News Service finance RSS and does not require a key. Keep `ENABLE_TMTPOST=false` unless the optional technology/business supplement is wanted, `ENABLE_CNBC_FALLBACK=true` for international fallback, and `ENABLE_JIN10=false` for the M10 free-source deployment. AI and push additionally require `ENABLE_AI=true`, `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL`, `ENABLE_PUSH=true`, and `WECOM_WEBHOOK_URL`.

Optional operational values include `MAX_ITEMS_PER_CYCLE`, `COLLECT_INTERVAL_SECONDS`, `PUSH_MIN_IMPORTANCE`, `QUIET_HOURS_START`, `QUIET_HOURS_END`, and `PUSH_DESTINATION`.

## 2. Start

The one-command deployment is `docker compose up --build -d`.

For an explicit first startup, run `docker compose build`, then `docker compose up -d postgres redis`, then `docker compose run --rm migrate`, and finally `docker compose up -d api worker`.

Compose waits for PostgreSQL and Redis health checks, runs `alembic upgrade head`, then starts API and worker.

## 3. Verify services

Run `docker compose ps`, request `http://localhost:8000/health` and `http://localhost:8000/ready`, and inspect `docker compose logs --tail=100 worker`. `/health` checks API liveness; `/ready` checks PostgreSQL and Redis. Worker logs should show a collection cycle with a non-zero `news_count`. Never paste the expanded Compose configuration or unredacted environment into support logs because it contains provider credentials.

## 4. First business run

Set `MAX_ITEMS_PER_CYCLE=1` for the first run and execute `docker compose exec worker python -m app.run_once`. The first M10 run creates and enables `event-analysis/m10-zh-v1` while retaining historical prompt versions. Confirm the Chinese AI output. A WeCom delivery is expected only when the existing Decision Engine accepts the event; events below `PUSH_MIN_IMPORTANCE` are correctly recorded as ignored.

## 5. Stop, upgrade, and backup

Use `docker compose logs -f worker`, `docker compose down`, and `docker compose up --build -d` for routine operations. Back up PostgreSQL before upgrades. Do not delete the `postgres_data` volume. Run the migration service before starting upgraded application containers.
