# Design: Swagger, Request ID Middleware, and Concurrency Handling

**Date:** 2026-06-09
**Project:** Deployment Tracker API
**Deployment target:** Multiple EC2 instances behind a load balancer

---

## 1. Swagger / OpenAPI

### Goal
Expose an interactive API explorer at `/api/schema/swagger-ui/` and a machine-readable schema at `/api/schema/` so consumers (and interviewers) can explore and test the API without reading source code.

### Approach
Use `drf-spectacular` (OpenAPI 3.0). It introspects DRF serializers, validators, and `@api_view` decorators with no per-view annotation required. The alternative (`drf-yasg`) is OpenAPI 2.0 only and requires more manual work.

### Changes

**`requirements.txt`**
```
drf-spectacular>=0.27
```

**`config/settings.py`**
```python
INSTALLED_APPS = [..., "drf_spectacular"]

SPECTACULAR_SETTINGS = {
    "TITLE": "Deployment Tracker API",
    "DESCRIPTION": "Internal observability API for deployment event history.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}
```

**`config/urls.py`** — add three routes:
```python
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

urlpatterns = [
    ...,
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
```

No changes to views.

---

## 2. Request ID Middleware

### Goal
Tag every HTTP request with a UUID, stamp it on all log lines produced during that request, and return it in the `X-Request-ID` response header. Enables instant log correlation in CloudWatch/Datadog when debugging production incidents across multiple EC2 instances.

### Behavior
- If the incoming request includes `X-Request-ID` header, use that value (load balancer or client supplied).
- Otherwise generate `uuid4()`.
- Store in `threading.local()` so the logging filter can read it without being passed explicitly.
- Return in `X-Request-ID` response header.

### Changes

**`config/middleware.py`** (new file)
```python
import uuid
import threading
import logging

_local = threading.local()

def get_request_id():
    return getattr(_local, "request_id", None)

class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get("HTTP_X_REQUEST_ID") or str(uuid.uuid4())
        _local.request_id = request_id
        request.request_id = request_id
        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        return response

class RequestIDFilter(logging.Filter):
    def filter(self, record):
        record.request_id = get_request_id() or "-"
        return True
```

**`config/settings.py`**
- Add `"config.middleware.RequestIDMiddleware"` to `MIDDLEWARE` (after `SecurityMiddleware`, before `CommonMiddleware`)
- Update `LOGGING` formatter: `"%(asctime)s [%(levelname)s] [%(request_id)s] %(name)s %(message)s"`
- Add filter to handler:
  ```python
  "filters": {"request_id": {"()": "config.middleware.RequestIDFilter"}},
  "handlers": {"console": {..., "filters": ["request_id"]}},
  ```

### Example log output
```
2026-06-09T10:23:01Z [INFO] [7f3a1b2c-...] deployments deployment_detail id=deploy_001 (from DB, cached for 300s)
2026-06-09T10:23:01Z [DEBUG] [7f3a1b2c-...] deployments Cache hit key=deployment:deploy_001
```

---

## 3. Concurrency Handling

### Deployment context
Multiple EC2 instances behind an ALB. Any two instances can receive conflicting writes simultaneously. The database is shared (single RDS/Postgres in prod). The cache is not currently shared.

### Problem A — Duplicate POST (IntegrityError → 500)

**Scenario:** Two instances receive `POST /deployments/` with `id="deploy_033"` at the same time. One wins, the other hits a database unique-constraint violation (`IntegrityError`) which is currently unhandled → returns 500.

**Fix:** Catch `IntegrityError` in `_create_deployment`, return `409 Conflict`.

```python
from django.db import IntegrityError

try:
    serializer.save()
except IntegrityError:
    logger.warning("Duplicate deployment id=%s", serializer.validated_data.get("id"))
    return Response({"error": "A deployment with this ID already exists."}, status=409)
```

### Problem B — Lost Update on PUT (last write wins)

**Scenario:** EC2-A and EC2-B both fetch `deploy_001`, modify it, and call `.save()`. The second `.save()` silently overwrites the first — no error, data lost.

**Fix:** Pessimistic locking using `select_for_update()` inside `transaction.atomic()`. The database acquires a row-level lock when the row is fetched; the second PUT blocks until the first transaction commits.

```python
from django.db import transaction

with transaction.atomic():
    deployment = Deployment.objects.select_for_update().get(pk=deployment_id)
    serializer = DeploymentSerializer(deployment, data=request.data)
    if serializer.is_valid():
        serializer.save()
        cache.delete(f"deployment:{deployment_id}")
        return Response(serializer.data)
```

**SQLite note:** SQLite uses a full database write lock (not row-level). This serializes all concurrent PUTs, which is acceptable in dev but is the reason to switch to Postgres in production.

### Problem C — Stale Cache Across EC2 Instances

**Scenario:** EC2-A handles a PUT for `deploy_001` and deletes `deployment:deploy_001` from its local LocMemCache. EC2-B still has the old value cached and will serve stale data for up to `DEPLOYMENT_CACHE_TTL` seconds.

**Root cause:** `LocMemCache` is per-process. Each EC2 instance has its own isolated cache.

**Fix:** Replace LocMemCache with Redis as the shared cache backend when `REDIS_URL` is set. Fall back to LocMemCache in dev (no `REDIS_URL`).

**`requirements.txt`**
```
django-redis>=5.4
```

**`config/settings.py`**
```python
import os

REDIS_URL = os.environ.get("REDIS_URL")

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "deployment-tracker",
        }
    }
```

**EC2 deploy**: set `REDIS_URL=redis://<elasticache-endpoint>:6379/0` in the environment. Add `EC2_REDIS_URL` to GitHub Actions secrets and inject it in the deploy step.

---

## New environment variables

| Variable | Default | Purpose |
|---|---|---|
| `REDIS_URL` | unset (uses LocMemCache) | Redis connection string for shared cache in multi-EC2 setup |

---

## Files changed

| File | Change |
|---|---|
| `requirements.txt` | Add `drf-spectacular>=0.27`, `django-redis>=5.4` |
| `config/settings.py` | Add `drf_spectacular` to INSTALLED_APPS, add SPECTACULAR_SETTINGS, update CACHES (Redis/LocMemCache conditional), update LOGGING (filter + format) |
| `config/middleware.py` | New file: `RequestIDMiddleware` + `RequestIDFilter` |
| `config/urls.py` | Add schema/swagger-ui/redoc routes |
| `deployments/views.py` | POST: catch IntegrityError → 409; PUT: select_for_update inside transaction.atomic() |
| `deployments/tests.py` | Add: duplicate POST → 409; concurrent PUT shape test |
| `docs/API.md` | Add 409 to POST error table, add `X-Request-ID` header note |
| `README.md` | Add `REDIS_URL` env var, Swagger UI URL, request ID header |
| `CLAUDE.md` | Add middleware name, REDIS_URL, Swagger routes |

---

## Verification

1. `python manage.py runserver` → open `http://localhost:8000/api/schema/swagger-ui/` — interactive UI shows all 4 endpoints
2. `curl -X POST /deployments/ <same payload twice>` → second returns 409 with `{"error": "A deployment with this ID already exists."}`
3. Any request → response headers include `X-Request-ID: <uuid>` and logs show `[<same-uuid>]`
4. `python manage.py test deployments --verbosity=2` — all tests pass including new ones
5. Set `REDIS_URL=redis://localhost:6379/0` + run Redis locally → cache operations use Redis (verify via `redis-cli monitor`)
