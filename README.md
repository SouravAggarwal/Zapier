# Deployment Tracker API

Backend service for ingesting and querying deployment event history across services.

## Setup (under 2 minutes)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_data
python manage.py runserver 0.0.0.0:8000
```

Server starts at `http://localhost:8000`.  
Interactive API docs: `http://localhost:8000/api/schema/swagger-ui/`

## Endpoints

### Interactive docs
```
GET /api/schema/swagger-ui/   — Swagger UI (try endpoints in browser)
GET /api/schema/redoc/        — ReDoc (read-only reference)
GET /api/schema/              — Raw OpenAPI YAML schema
```

### 1. List deployments

```
GET /deployments/
```

**Query parameters**

| Param | Type | Description |
|---|---|---|
| `service` | string | Filter by service (`billing-api`, `auth-service`, `payment-processor`, `notification-service`) |
| `status` | string | Filter by status (`success`, `failed`, `running`) |
| `timestamp_after` | ISO 8601 | Return deployments at or after this datetime |
| `timestamp_before` | ISO 8601 | Return deployments at or before this datetime |
| `limit` | int | Page size (default 20, max 100) |
| `offset` | int | Pagination offset (default 0) |

**Response — 200**
```json
{
  "count": 32,
  "next_offset": 20,
  "previous_offset": null,
  "results": [
    {
      "id": "deploy_001",
      "service": "billing-api",
      "status": "success",
      "duration": 180,
      "timestamp": "2025-04-01T08:00:00Z",
      "commit_sha": "a1b2c3d"
    }
  ]
}
```

```bash
curl "http://localhost:8000/deployments/?service=billing-api&status=failed&limit=10"
curl "http://localhost:8000/deployments/?timestamp_after=2025-05-01T00:00:00Z"
```

### 2. Get a deployment

```
GET /deployments/<id>/
```

Served from in-memory cache after first fetch (default TTL 300s). Returns `200` on success, `404` if not found.

```bash
curl http://localhost:8000/deployments/deploy_001/
```

### 3. Create a deployment

```
POST /deployments/
Content-Type: application/json
```

Returns `201` on success, `400` on validation error, `409` if the ID already exists (concurrent duplicate).

```bash
curl -X POST http://localhost:8000/deployments/ \
  -H "Content-Type: application/json" \
  -d '{"id":"deploy_033","service":"auth-service","status":"success","duration":90,"timestamp":"2025-06-09T10:00:00Z","commit_sha":"abc1234"}'
```

### 4. Update a deployment

```
PUT /deployments/<id>/
Content-Type: application/json
```

Full replacement. Uses `SELECT FOR UPDATE` row-level locking to prevent lost writes under concurrent updates. Invalidates cache on success.

Returns `200` on success, `400` on validation error, `404` if not found.

```bash
curl -X PUT http://localhost:8000/deployments/deploy_001/ \
  -H "Content-Type: application/json" \
  -d '{"id":"deploy_001","service":"billing-api","status":"failed","duration":320,"timestamp":"2025-04-01T08:00:00Z","commit_sha":"a1b2c3d"}'
```

## Validation rules

| Field | Rule |
|---|---|
| `service` | One of the 4 known services |
| `status` | `success`, `failed`, or `running` |
| `commit_sha` | 7–40 lowercase hex characters |
| `duration` | Positive integer (seconds) |

## Request tracing

Every response includes an `X-Request-ID` header (UUID). The same ID is stamped on every log line produced during that request. To correlate logs for a specific request, grep for its ID.
If client sends `X-Request-ID`, that value is used instead of generating a new one.

## Concurrency safety

| Scenario | Behaviour |
|---|---|
| Two POSTs with the same `id` race | First wins; second gets `409 Conflict` |
| Two PUTs on the same record race | DB row lock (`SELECT FOR UPDATE`) serializes them — no lost writes |

## Running tests

```bash
python manage.py test deployments --verbosity=2
```

## Linting

```bash
flake8 deployments config --max-line-length=120 --exclude=migrations
```

## Design notes

- Storage: PostgreSQL in production, SQLite in dev (controlled via `DB_ENGINE` env var)
- Cache: in-process LocMemCache (no external dependency)
- Logging: structured ISO 8601 timestamps + `[request-id]` on every line
- No authentication — internal observability service
- Results sorted newest-first by default

---

## Production Setup (if required)

> Everything below applies to production deployments. Local development works out of the box with the defaults above.

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | insecure dev key | Set a strong random value in production |
| `DEBUG` | `True` | Set to `False` in production |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated list of allowed hostnames |
| `DEPLOYMENT_CACHE_TTL` | `300` | Cache TTL in seconds for single-deployment lookups |
| `DB_ENGINE` | unset (SQLite) | Set to `postgresql` to switch to PostgreSQL |
| `DB_NAME` | `deployment_tracker` | PostgreSQL database name |
| `DB_USER` | `postgres` | PostgreSQL user |
| `DB_PASSWORD` | _(empty)_ | PostgreSQL password |
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |

Copy `.env.example` to `.env` and fill in your values — it is loaded automatically at startup.

### PostgreSQL

```bash
createdb deployment_tracker

DB_ENGINE=postgresql DB_NAME=deployment_tracker DB_USER=<user> DB_PASSWORD=<pass> \
  python manage.py migrate
python manage.py seed_data
python manage.py runserver
```

### CI / Deploy

GitHub Actions (`.github/workflows/ci-deploy.yml`) runs tests + lint on every push and deploys to EC2 on push to `main`. Add these secrets in your repository's **Settings → Secrets and variables → Actions**:

| Secret | Description |
|---|---|
| `EC2_HOST` | EC2 public IP or hostname |
| `EC2_USER` | SSH user (e.g. `ubuntu`) |
| `EC2_KEY` | Private SSH key content |
| `EC2_PATH` | Absolute path to the project on the server |
