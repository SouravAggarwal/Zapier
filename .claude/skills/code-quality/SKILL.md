---
name: code-quality
description: >
  Code quality, linting, and style rules for this Django REST Framework project.
  Use this skill whenever writing, reviewing, or refactoring any Python, Django,
  or DRF code in this repo — including models, serializers, views, services,
  tests, middleware, settings, and admin. Also use it before running flake8,
  suggesting code changes, or checking if existing code follows project conventions.
---

# Code Quality — Python · Django · DRF

This skill captures the conventions this project actually uses. When writing or
reviewing code, treat deviations from these rules as bugs, not style preferences.

---

## 1. Flake8 — Linting

### Run linting

```bash
flake8 deployments/ config/
```

A `.flake8` config lives at the project root — always use it rather than passing
flags by hand.

### `.flake8` configuration (project root)

```ini
[flake8]
max-line-length = 100
exclude =
    venv,
    .git,
    __pycache__,
    deployments/migrations,
    deployments/management/commands/seed_data.py
extend-ignore =
    # whitespace before ':' (conflicts with black slice syntax)
    E203,
    # line break before binary operator (W504 is the preferred alternative)
    W503
per-file-ignores =
    # migrations are auto-generated — don't enforce line length there
    deployments/migrations/*.py: E501
```

Create this file if it doesn't exist yet (`touch .flake8` and paste the above).

### Key rules enforced

| Code | Rule | Example violation |
|------|------|-------------------|
| E501 | Line too long (> 100 chars) | Long log messages, SQL strings |
| E302 | Expected 2 blank lines before class/function | Single blank line before `class Foo:` |
| E303 | Too many blank lines | Three blank lines anywhere |
| E711 | Comparison to None via `==` | `if x == None` → use `if x is None` |
| E712 | Comparison to True/False | `if x == True` → use `if x` |
| F401 | Imported but unused | Leftover imports after refactor |
| F811 | Redefinition of unused name | Importing same name twice |
| W291 | Trailing whitespace | Spaces at end of line |
| W293 | Whitespace on blank line | Blank line with spaces |
| W605 | Invalid escape sequence | `"\d+"` → use `r"\d+"` |

### Flake8 suppressions

Only suppress when unavoidable, always with a comment explaining why:

```python
result = some_long_function_name(arg1, arg2)  # noqa: E501 — generated URL can't be shortened
```

Never suppress F401 or F811 — remove the unused import instead.

---

## 2. Python Style

### Line length

Hard limit: **100 characters**. Break long lines using implicit continuation
inside brackets — never use backslash continuation.

```python
# Good — implicit continuation
response = Response(
    {"error": f"No deployment found with id '{deployment_id}'."},
    status=status.HTTP_404_NOT_FOUND,
)

# Bad — backslash
response = Response({"error": f"No deployment found with id '{deployment_id}'."}, \
    status=status.HTTP_404_NOT_FOUND)
```

### Quotes

Use **single quotes** for all strings. Use double quotes only inside a string
that contains a single quote, to avoid escaping.

```python
# Good
service = "billing-api"
message = "it's a valid deployment"

# Bad
service = "billing-api"   # unnecessary double quotes
```

### Blank lines

- 2 blank lines between top-level definitions (classes, module-level functions)
- 1 blank line between methods inside a class
- 1 blank line between logical sections inside a function body
- 0 blank lines between a class definition and its first docstring or method

### Imports — order and grouping

Follow PEP 8. Three groups, separated by blank lines, in this order:

```python
# 1. Standard library
import logging
from threading import local

# 2. Third-party (Django, DRF, drf-spectacular)
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

# 3. Local (relative imports, same package)
from .models import Deployment
from .serializers import DeploymentSerializer
from .services.cache import deployment_cache
```

Rules:
- Never use wildcard imports (`from django.db import *`)
- Always use relative imports for intra-app modules (`.models`, not `deployments.models`)
- Remove unused imports immediately — don't comment them out

### Naming

| Kind | Convention | Example |
|------|-----------|---------|
| Classes | PascalCase | `DeploymentListView`, `CacheService` |
| Functions & methods | snake_case | `validate_timestamp`, `get_request_id` |
| Variables & params | snake_case | `deployment_id`, `cache_key` |
| Module-level constants | UPPER_SNAKE_CASE | `SERVICE_CHOICES`, `DEPLOYMENT_CACHE_TTL` |
| Private attrs/methods | leading underscore | `_prefix`, `_key()` |
| Test helpers | leading underscore | `_make()`, `_valid_body()` |

### Type hints

Use type hints on service-layer classes and standalone utility functions.
Views and serializers are exempt (DRF provides runtime type checking via
serializer fields). Models are exempt (Django ORM handles types at the field level).

```python
# Good — service layer
class CacheService:
    def __init__(self, prefix: str, ttl: int) -> None:
        self._prefix = prefix
        self._ttl = ttl

    def get(self, identifier: str):  # return type is Any — omit rather than type: ignore
        return cache.get(self._key(identifier))
```

### f-strings

Always prefer f-strings over `.format()` or `%` formatting:

```python
# Good
logger.info("deployment_detail id=%s (from DB, cached for %ds)", deployment_id, ttl)
raise ValueError(f"Unknown service: {service!r}")

# Bad
raise ValueError("Unknown service: %r" % service)
raise ValueError("Unknown service: {}".format(service))
```

Note: keep `%s`-style formatting in logger calls (not f-strings) — this defers
string interpolation until the log record is actually emitted, which is more
efficient when the log level is suppressed.

### Comments

Write comments only when the *why* is non-obvious. Good comment targets:
- Hidden constraints (`# SQLite doesn't support select_for_update across connections`)
- Workarounds (`# DRF's UniqueValidator runs before our validate_* methods`)
- Non-obvious invariants (`# cache.set is atomic in LocMemCache — no lock needed`)

Never comment *what* the code does — well-named identifiers already do that.

---

## 3. Django Models

### Field ordering inside a model

```python
class Deployment(models.Model):
    # 1. Primary key (if custom)
    id = models.CharField(max_length=50, primary_key=True)

    # 2. Business / domain fields (in logical grouping order)
    service   = models.CharField(max_length=100, db_index=True, choices=SERVICE_CHOICES)
    status    = models.CharField(max_length=20,  db_index=True, choices=STATUS_CHOICES)
    duration  = models.IntegerField(help_text="Duration in seconds")
    timestamp = models.DateTimeField(db_index=True)
    commit_sha = models.CharField(max_length=40, help_text="7–40 hex chars")

    # 3. Audit fields (always last)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # 4. Meta, then __str__, then custom methods
    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.id} ({self.service} — {self.status})"
```

### Model rules

- Define choices as **module-level lists** of 2-tuples, not inside the class
- Add `db_index=True` to any field used in `.filter()` or `.order_by()`
- Always provide `help_text` for non-obvious fields
- Always implement `__str__` — use an f-string, include the PK and one identifying field
- Keep `Meta` minimal — only `ordering` if needed; don't add `verbose_name` unless
  the admin needs it
- Never use `null=True` on string fields (`CharField`, `TextField`) — use `blank=True`
  and empty string as the sentinel; only use `null=True` on non-string fields that
  are genuinely optional

### ORM query rules

- Use `.filter()` for all conditional queries — never raw SQL
- Use `select_for_update()` inside `transaction.atomic()` for any read-modify-write
  operation that must be race-safe
- Avoid N+1: if you need a related field for every item in a queryset, add
  `select_related()` or `prefetch_related()` at the queryset level
- Slice querysets for pagination (`queryset[offset:offset + limit]`) — never
  load the full queryset and slice in Python

---

## 4. DRF Serializers

### Structure

```python
class DeploymentSerializer(serializers.ModelSerializer):
    """Serializes Deployment instances; field-level validators enforce constraints."""

    # 1. Explicit field declarations (override DRF defaults or add validators)
    duration = serializers.IntegerField(min_value=1, help_text="Duration in seconds")
    commit_sha = serializers.CharField(
        max_length=40,
        validators=[RegexValidator(r"^[0-9a-f]{7,40}$", "must be 7–40 lowercase hex")],
    )

    # 2. Field-level validators (validate_<fieldname>)
    def validate_timestamp(self, value):
        if value > now() + timedelta(days=1):
            raise serializers.ValidationError("timestamp cannot be more than 1 day in the future.")
        return value

    # 3. Meta
    class Meta:
        model = Deployment
        fields = [
            "id", "service", "status", "duration", "timestamp",
            "commit_sha", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]
```

### Serializer rules

- Never use `fields = "__all__"` — enumerate every field explicitly so additions
  to the model don't leak silently into the API
- Declare `read_only_fields` for auto-set fields (`created_at`, `updated_at`, etc.)
- Put field-level validation in `validate_<fieldname>` methods — not in `validate()`
  unless the validation requires comparing multiple fields
- Use `serializers.ValidationError` (not `ValueError`) so DRF normalizes the
  error response through the custom exception handler
- Separate serializers for separate concerns:
  - `DeploymentSerializer` — create/update/read of a single resource
  - `DeploymentFilterSerializer` — validates query params for list endpoints
  - `DeploymentListResponseSerializer` — pagination envelope (if used in schema)

---

## 5. DRF Views

### Class-based views (APIView)

Use `APIView` subclasses, not function-based views or ViewSets. One class per
URL pattern, with one method per HTTP verb.

```python
@deployment_detail_schema
class DeploymentDetailView(APIView):
    """Retrieve (GET) or fully update (PUT) a single deployment by ID."""

    def get(self, request, deployment_id):
        """Serve from in-memory cache; fall back to DB on miss."""
        ...

    def put(self, request, deployment_id):
        """Full update with pessimistic row lock to prevent lost writes."""
        ...
```

### Error handling in views

Always catch exceptions explicitly and return a `Response` with `{"error": "..."}`.
Never let Django's 500 handler surface to the client.

```python
# Good
try:
    deployment = Deployment.objects.get(pk=deployment_id)
except Deployment.DoesNotExist:
    logger.warning("Deployment not found id=%s", deployment_id)
    return Response(
        {"error": f"No deployment found with id '{deployment_id}'."},
        status=status.HTTP_404_NOT_FOUND,
    )

# Bad — never use get_object_or_404 in API views
# (it raises Http404 which may render HTML, not JSON)
deployment = get_object_or_404(Deployment, pk=deployment_id)
```

### Response shape

Every endpoint returns one of exactly three shapes — never deviate:

```python
# List response (GET /deployments/)
{
    "count": 32,
    "next_offset": 20,      # or null if no next page
    "previous_offset": 0,   # or null if on first page
    "results": [...]
}

# Single resource (GET /deployments/<id>/, PUT /deployments/<id>/, POST /deployments/)
{
    "id": "deploy_001",
    "service": "billing-api",
    "status": "success",
    "duration": 180,
    "timestamp": "2025-04-01T08:00:00Z",
    "commit_sha": "a1b2c3d",
    "created_at": "...",
    "updated_at": "..."
}

# Error (any 4xx or 5xx)
{"error": "descriptive message"}
```

### Logging in views

Log every significant outcome. Use the `deployments` logger, not `print()`.

```python
logger = logging.getLogger("deployments")

# INFO — successful operations that callers care about
logger.info("deployment_detail id=%s (from DB, cached for %ds)", deployment_id, ttl)
logger.info("Deployment created id=%s service=%s", id, service)
logger.info("Deployment updated id=%s, cache invalidated", deployment_id)

# DEBUG — internal state useful during development
logger.debug("Cache hit id=%s", deployment_id)
logger.debug("Cache miss id=%s", deployment_id)

# WARNING — caller errors (invalid input, missing resource)
logger.warning("Deployment not found id=%s", deployment_id)
logger.warning("Deployment create failed: %s", serializer.errors)
logger.warning("Invalid list filters: %s", filter_serializer.errors)
```

Use `%s`-style formatting in all logger calls (not f-strings).

### Validation flow in views

```python
# Validate → serialize → persist → respond
serializer = DeploymentSerializer(data=request.data)
if not serializer.is_valid():
    logger.warning("Deployment create failed: %s", serializer.errors)
    return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

serializer.save()
return Response(serializer.data, status=status.HTTP_201_CREATED)
```

---

## 6. Service Layer

Services live in `deployments/services/`. Each file is a focused module with one
clear responsibility. The `__init__.py` stays empty.

### CacheService pattern

```python
# deployments/services/cache.py

class CacheService:
    def __init__(self, prefix: str, ttl: int) -> None:
        self._prefix = prefix
        self._ttl = ttl

    def _key(self, identifier: str) -> str:
        return f"{self._prefix}:{identifier}"

    def get(self, identifier: str):
        return cache.get(self._key(identifier))

    def set(self, identifier: str, data) -> None:
        cache.set(self._key(identifier), data, timeout=self._ttl)

    def invalidate(self, identifier: str) -> None:
        cache.delete(self._key(identifier))


# Module-level instance — import this, not CacheService directly
deployment_cache = CacheService("deployment", ttl=settings.DEPLOYMENT_CACHE_TTL)
```

Rules for new services:
- Instantiate at module level when the service has no per-request state
- Keep services ignorant of HTTP — no `Request`, `Response`, or status codes
- Services do not log — logging belongs in views, which have request context
- Use type hints on `__init__` and public methods

---

## 7. Configuration & Settings

### Settings patterns

```python
# Read from environment with a safe default
DEPLOYMENT_CACHE_TTL = int(os.environ.get("DEPLOYMENT_CACHE_TTL", 300))

# Never hardcode secrets — always read from env
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-key-change-in-production")
```

- Use `os.environ.get(KEY, default)` — never `os.environ[KEY]` (raises KeyError in production)
- Cast environment variables at read time (`int()`, `bool()`) — don't scatter casts
  throughout the codebase
- Keep `DEBUG = True` only as a fallback for local dev; production sets `DEBUG=False`

---

## 8. Tests

### Test file structure

```python
# Helpers — module level, not inside any class
def _make(dep_id="deploy_t01", ...):   # creates a Deployment in the DB
    ...

def _valid_body(**overrides):           # returns a valid POST/PUT payload dict
    ...

# Test classes — one per feature or layer
class CacheServiceTests(TestCase): ...
class DeploymentModelTests(TestCase): ...
class ListTests(TestCase): ...
class DetailTests(TestCase): ...
class CreateTests(TestCase): ...
class UpdateTests(TestCase): ...
class MiddlewareTests(TestCase): ...
```

### Test rules

- Call `cache.clear()` in `setUp()` for any test class that touches HTTP endpoints
- Use `assertNumQueries(N)` to assert cache hit/miss behaviour — zero queries = cache hit
- Use `self.assertLogs("deployments", level="INFO")` to verify log output for
  significant operations (not for every test — only where logging is part of the contract)
- Use `patch.object(Serializer, "save", side_effect=IntegrityError)` for race condition
  tests — don't try to reproduce the race with threads in unit tests
- Test names should describe the scenario in plain English:
  `test_put_updates_data_and_invalidates_cache_with_log` not `test_put_200`
- Keep test setup minimal — `_make()` for DB objects, `_valid_body()` for request payloads
- Don't assert on log messages character-for-character — assert that a substring
  appears (`any("not found" in line for line in cm.output)`)

### What to test (minimum bar)

For every endpoint: happy path, one validation failure (400), not-found (404).
For cache: verify second request uses 0 queries.
For models: verify auto-set fields (`created_at`, `updated_at`) behave correctly.
For services: test the lifecycle in one test (miss → set → hit → invalidate → miss).

---

## 9. Error Handling Conventions

### Exception handler

All exceptions are normalized by `config/exceptions.py` to `{"error": "..."}`.
Do not bypass this — never return raw exception messages or Django's default
error pages from an API view.

### Integrity errors

Catch `IntegrityError` at the view level for concurrent duplicate detection → 409:

```python
try:
    serializer.save()
except IntegrityError:
    logger.warning("Duplicate deployment id=%s (race condition)", id)
    return Response({"error": "A deployment with this ID already exists."}, status=409)
```

Sequential duplicates are caught earlier by DRF's `UniqueValidator` → 400.

---

## 10. Quick Checklist

Before submitting any code change, verify:

- [ ] `flake8 deployments/ config/` passes with zero output
- [ ] No unused imports (`F401`)
- [ ] No trailing whitespace (`W291`, `W293`)
- [ ] Lines ≤ 100 chars (except auto-generated migrations)
- [ ] Single quotes used for strings
- [ ] 2 blank lines before every top-level class or function
- [ ] Logger calls use `%s` format, not f-strings
- [ ] Every new model has `__str__` and audit fields (`created_at`, `updated_at`)
- [ ] Serializer `fields` list is explicit — no `"__all__"`
- [ ] Views catch `DoesNotExist` explicitly (not `get_object_or_404`)
- [ ] Response shape matches one of the three defined shapes above
- [ ] New tests call `cache.clear()` in `setUp()` if they hit HTTP endpoints
- [ ] New service classes have type hints on `__init__` and public methods
