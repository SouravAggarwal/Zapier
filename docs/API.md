# API Reference

Base URL: `http://localhost:8000` (dev) / your EC2 hostname (prod)

Interactive docs: `http://localhost:8000/api/schema/swagger-ui/`

All responses are `application/json`. All errors use `{"error": "..."}` format.
Every response includes an `X-Request-ID` header for log correlation.

---

## GET /deployments/

List deployments with optional filtering and pagination.

### Query parameters

| Param | Type | Default | Description |
|---|---|---|---|
| `service` | string | — | `billing-api`, `auth-service`, `payment-processor`, `notification-service` |
| `status` | string | — | `success`, `failed`, `running` |
| `timestamp_after` | ISO 8601 | — | Include deployments at or after this datetime |
| `timestamp_before` | ISO 8601 | — | Include deployments at or before this datetime |
| `limit` | integer | `20` | Page size (max 100) |
| `offset` | integer | `0` | Number of records to skip |

### Response — 200

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

### Response — 400

```json
{ "error": "Invalid service 'x'. Valid options: billing-api, auth-service, payment-processor, notification-service." }
{ "error": "Invalid 'timestamp_after'. Use ISO 8601 format (e.g. 2025-04-01T00:00:00Z)." }
{ "error": "'limit' cannot exceed 100." }
```

---

## POST /deployments/

Create a new deployment record.

### Request body

```json
{
  "id": "deploy_033",
  "service": "auth-service",
  "status": "success",
  "duration": 90,
  "timestamp": "2025-06-09T10:00:00Z",
  "commit_sha": "abc1234"
}
```

### Validation rules

| Field | Rule |
|---|---|
| `id` | Non-empty string, max 50 characters, must be unique |
| `service` | One of the 4 known services |
| `status` | `success`, `failed`, or `running` |
| `duration` | Positive integer (seconds) |
| `commit_sha` | 7–40 lowercase hex characters |

### Response — 201: Created deployment object

### Response — 400: Validation error

```json
{ "error": { "commit_sha": ["commit_sha must be 7–40 lowercase hex characters."] } }
```

### Response — 409: Concurrent duplicate ID (race condition)

```json
{ "error": "A deployment with this ID already exists." }
```

---

## GET /deployments/\<id\>/

Fetch a single deployment by ID. Served from cache after first request (default TTL 300s).

### Response — 200: Deployment object

### Response — 404

```json
{ "error": "No deployment found with id 'deploy_999'." }
```

---

## PUT /deployments/\<id\>/

Full update. Uses `SELECT FOR UPDATE` to prevent lost writes under concurrent requests. Invalidates cache on success. All fields required.

### Response — 200: Updated deployment object

### Response — 400: Validation error

```json
{ "error": { "status": ["\"badstatus\" is not a valid choice."] } }
```

### Response — 404

```json
{ "error": "No deployment found with id 'deploy_999'." }
```

---

## Error codes summary

| Code | When |
|---|---|
| 400 | Invalid query params or request body |
| 404 | Deployment ID does not exist |
| 405 | Method not allowed (e.g. DELETE) |
| 409 | Concurrent duplicate create |

---

## Request tracing

Every response includes `X-Request-ID`. Pass `X-Request-ID: <your-id>` in the request to propagate a trace ID from your load balancer or upstream service.

```bash
curl -H "X-Request-ID: my-trace-123" http://localhost:8000/deployments/
# Response headers will include: X-Request-ID: my-trace-123
```
