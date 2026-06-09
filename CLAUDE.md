# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Deployment Tracker — Claude Context

Django REST Framework API for querying and managing deployment event history across services.

## Commands

All commands must be run inside the virtual environment. Activate with `source venv/bin/activate` or prefix with `venv/bin/python` / `venv/bin/flake8`.

```bash
# Run all tests
venv/bin/python manage.py test

# Run a single test class
venv/bin/python manage.py test deployments.tests.CreateTests

# Run a single test method
venv/bin/python manage.py test deployments.tests.CreateTests.test_post_creates_deployment

# Lint
venv/bin/python -m flake8 deployments/ config/

# Apply migrations
venv/bin/python manage.py migrate

# Load seed data (32 mock deployments)
venv/bin/python manage.py seed_data

# Start dev server
venv/bin/python manage.py runserver
```

## Architecture

The project is a single Django app (`deployments`) with a thin `config` package for project-level settings, middleware, and URL routing.

**Request lifecycle:**
1. `config/middleware.py` — `RequestIDMiddleware` attaches a UUID to every request (propagates incoming `X-Request-ID` if present, otherwise generates one). Stored in `threading.local()` so `RequestIDFilter` can stamp it on every log line without passing it explicitly.
2. `deployments/views.py` — `DeploymentListView` and `DeploymentDetailView` are `APIView` subclasses. Views validate input via serializers, hit the ORM, manage the cache, and log outcomes.
3. `deployments/services/cache.py` — all cache access goes through the module-level `deployment_cache` instance (`CacheService`). Never call `django.core.cache.cache` directly in views.
4. `config/exceptions.py` — normalizes all DRF exceptions to `{"error": "..."}`.

**Schema separation:** OpenAPI decorators (`drf-spectacular`) live in `deployments/schemas.py` as view decorators, keeping views clean.

**Serializers:** Three serializers with distinct roles — `DeploymentSerializer` (create/read/update), `DeploymentFilterSerializer` (validates query params), `DeploymentListResponseSerializer` (pagination envelope for schema docs only).

**Concurrency model:** PUT uses `select_for_update()` inside `transaction.atomic()` for pessimistic row locking. POST catches `IntegrityError` → 409 as a safety net for concurrent duplicate IDs (sequential duplicates are caught earlier by `UniqueValidator` → 400).

## Key files

- `deployments/models.py` — `Deployment` model + `SERVICE_CHOICES` / `STATUS_CHOICES` constants
- `deployments/serializers.py` — `DeploymentSerializer`, `DeploymentFilterSerializer`, `DeploymentListResponseSerializer`
- `deployments/views.py` — `DeploymentListView` (GET/POST) and `DeploymentDetailView` (GET/PUT)
- `deployments/schemas.py` — drf-spectacular decorators (`deployment_list_schema`, `deployment_detail_schema`)
- `deployments/services/cache.py` — `CacheService` class + module-level `deployment_cache` instance
- `deployments/urls.py` — URL routing for `/deployments/` and `/deployments/<id>/`
- `deployments/tests.py` — tests covering endpoints, filters, cache, concurrency, and validation
- `deployments/admin.py` — `DeploymentAdmin` registered with list/filter/search
- `deployments/management/commands/seed_data.py` — loads 32 mock events across 4 services
- `config/settings.py` — Django + DRF config, conditional DB/cache, structured logging, dotenv load
- `config/exceptions.py` — custom DRF exception handler normalizing errors to `{"error": "..."}`
- `config/middleware.py` — `RequestIDMiddleware` + `RequestIDFilter`
- `config/urls.py` — includes deployment routes + Swagger UI / ReDoc / schema routes
- `.github/workflows/ci-deploy.yml` — CI (test + lint) + EC2 deploy on push to main
- `.env.example` — copy to `.env` for local dev; loaded automatically via `python-dotenv`

## Run locally

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # edit values if needed
python manage.py migrate
python manage.py seed_data
python manage.py runserver
```

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | insecure dev key | Set in production |
| `DEBUG` | `True` | Set `False` in production |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated |
| `DEPLOYMENT_CACHE_TTL` | `300` | Cache TTL in seconds |
| `DB_ENGINE` | unset (SQLite) | Set to `postgresql` for Postgres |
| `DB_NAME` | `deployment_tracker` | Postgres DB name |
| `DB_USER` | `postgres` | Postgres user |
| `DB_PASSWORD` | _(empty)_ | Postgres password |
| `DB_HOST` | `localhost` | Postgres host |
| `DB_PORT` | `5432` | Postgres port |
| `DB_CONN_MAX_AGE` | `60` | Postgres persistent connection lifetime (seconds) |

## API surface

| Method | Path | Description |
|---|---|---|
| GET | `/deployments/` | List with filters + pagination |
| POST | `/deployments/` | Create a deployment |
| GET | `/deployments/<id>/` | Fetch one (cached) |
| PUT | `/deployments/<id>/` | Full update (pessimistic lock + cache invalidation) |
| GET | `/api/schema/swagger-ui/` | Swagger UI |
| GET | `/api/schema/redoc/` | ReDoc |
| GET | `/api/schema/` | Raw OpenAPI YAML |

## Pagination envelope (GET /deployments/)

```json
{
  "count": 32,
  "next_offset": 20,
  "previous_offset": null,
  "results": [...]
}
```

## Single-deployment response shape

```json
{
  "id": "deploy_001",
  "service": "billing-api",
  "status": "success",
  "duration": 180,
  "timestamp": "2025-04-01T08:00:00Z",
  "commit_sha": "a1b2c3d",
  "created_at": "2025-04-01T08:00:00Z",
  "updated_at": "2025-04-01T08:00:00Z"
}
```

## Design conventions

- All errors return `{"error": "..."}` — enforced via `config/exceptions.py`
- Cache key pattern: `deployment:{id}` — in-process LocMemCache, TTL = `DEPLOYMENT_CACHE_TTL` seconds
- Cache is invalidated on PUT via `deployment_cache.invalidate(id)` inside `transaction.atomic()`
- Logger name: `deployments` — format: `%(asctime)s [%(levelname)s] [%(request_id)s] %(name)s %(message)s`
- Request ID: UUID per request, stored in `threading.local()`, echoed in `X-Request-ID` response header; incoming `X-Request-ID` header is propagated if present (allows upstream trace ID passthrough)
- PUT uses `select_for_update()` inside `transaction.atomic()` — row-level lock prevents lost updates
- POST catches `IntegrityError` → 409 (race condition safety net; sequential duplicates return 400 via UniqueValidator)
- Views are class-based (`APIView` subclasses) — one class per URL, one method per HTTP verb
- OpenAPI schema annotations live in `deployments/schemas.py`, not inline in views
- Cache access goes through `deployment_cache` (module-level `CacheService` instance) — never call `django.core.cache.cache` directly in views
- Services: `billing-api`, `auth-service`, `payment-processor`, `notification-service`
- Statuses: `success`, `failed`, `running`
- `commit_sha`: 7–40 lowercase hex characters
- `duration`: positive integer (seconds)
- SQLite in dev, PostgreSQL in prod (set `DB_ENGINE=postgresql`)

## GitHub Actions

CI runs on every push and PR (Python 3.12). Deploy to EC2 runs on push to `main` only when:
- `EC2_HOST`, `EC2_USER`, `EC2_KEY`, `EC2_PATH` secrets are set (repo Settings > Secrets)
- `DEPLOY_ENABLED=true` variable is set (repo Settings > Variables)
