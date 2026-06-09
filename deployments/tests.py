"""
Test suite for the Deployment Tracker API.

Covers: cache service, model timestamps, list/detail/create/update endpoints,
input validation, cache behaviour, and logging output.
"""
from unittest.mock import patch

from django.core.cache import cache
from django.db import IntegrityError
from django.test import TestCase
from django.utils.timezone import datetime, make_aware, now, timedelta
from rest_framework.test import APIClient

from deployments.services.cache import CacheService
from deployments.models import Deployment
from deployments.serializers import DeploymentSerializer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make(dep_id="deploy_t01", service="billing-api", dep_status="success",
          duration=120, commit_sha="abc1234", timestamp=None):
    if timestamp is None:
        timestamp = make_aware(datetime(2025, 5, 1, 12, 0, 0))
    return Deployment.objects.create(
        id=dep_id, service=service, status=dep_status,
        duration=duration, timestamp=timestamp, commit_sha=commit_sha,
    )


def _valid_body(**overrides):
    base = {
        "id": "new_001",
        "service": "auth-service",
        "status": "success",
        "duration": 90,
        "timestamp": "2025-05-01T10:00:00Z",
        "commit_sha": "abc1234",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# CacheService
# ---------------------------------------------------------------------------

class CacheServiceTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_get_set_invalidate_lifecycle(self):
        svc = CacheService("dep", ttl=60)
        self.assertIsNone(svc.get("x"))
        svc.set("x", {"v": 1})
        self.assertEqual(svc.get("x"), {"v": 1})
        svc.invalidate("x")
        self.assertIsNone(svc.get("x"))

    def test_prefix_isolation(self):
        a = CacheService("alpha", ttl=60)
        b = CacheService("beta", ttl=60)
        a.set("key", "from-alpha")
        self.assertIsNone(b.get("key"))


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class DeploymentModelTests(TestCase):
    def test_timestamps_auto_populated_and_created_at_immutable(self):
        dep = _make()
        self.assertIsNotNone(dep.created_at)
        original_created = dep.created_at
        original_updated = dep.updated_at
        dep.duration = 999
        dep.save()
        self.assertEqual(dep.created_at, original_created)
        self.assertGreater(dep.updated_at, original_updated)


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------

class ListTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        _make("d1", "billing-api", "success", timestamp=make_aware(datetime(2025, 4, 1)))
        _make("d2", "auth-service", "failed", timestamp=make_aware(datetime(2025, 5, 1)))
        _make("d3", "billing-api", "running", timestamp=make_aware(datetime(2025, 6, 1)))

    def test_list_filters_pagination_and_logs(self):
        with self.assertLogs("deployments", level="INFO") as cm:
            resp = self.client.get(
                "/deployments/?service=billing-api&status=success"
                "&timestamp_after=2025-01-01T00:00:00Z&limit=1&offset=0"
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 1)
        for key in ("count", "results", "next_offset", "previous_offset"):
            self.assertIn(key, resp.data)
        self.assertIsNone(resp.data["next_offset"])
        self.assertTrue(any("deployment_list" in line for line in cm.output))

    def test_invalid_params_return_400_with_log(self):
        with self.assertLogs("deployments", level="WARNING") as cm:
            resp = self.client.get("/deployments/?service=bad-service")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.data)
        self.assertTrue(any("Invalid list filters" in line for line in cm.output))

        self.assertEqual(
            self.client.get("/deployments/?timestamp_after=not-a-date").status_code, 400
        )
        self.assertEqual(self.client.get("/deployments/?limit=999").status_code, 400)


# ---------------------------------------------------------------------------
# Detail endpoint
# ---------------------------------------------------------------------------

class DetailTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.dep = _make()

    def test_detail_response_shape_and_cache(self):
        url = f"/deployments/{self.dep.id}/"
        with self.assertNumQueries(1):
            resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["id"], self.dep.id)
        for field in ("created_at", "updated_at"):
            self.assertIn(field, resp.data)
        with self.assertNumQueries(0):
            self.client.get(url)

    def test_detail_not_found_logs_warning(self):
        with self.assertLogs("deployments", level="WARNING") as cm:
            resp = self.client.get("/deployments/does-not-exist/")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("error", resp.data)
        self.assertTrue(any("not found" in line for line in cm.output))


# ---------------------------------------------------------------------------
# Create endpoint
# ---------------------------------------------------------------------------

class CreateTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_valid_create_returns_201(self):
        resp = self.client.post("/deployments/", _valid_body(), format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["id"], "new_001")
        for field in ("created_at", "updated_at"):
            self.assertIn(field, resp.data)

    def test_invalid_inputs_return_400(self):
        # bad field values
        resp = self.client.post(
            "/deployments/",
            _valid_body(service="bad", commit_sha="NOTHEX", duration=-1),
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.data)

        # timestamp more than 1 day in the future
        far_future = (now() + timedelta(days=2)).isoformat()
        resp = self.client.post(
            "/deployments/", _valid_body(id="new_002", timestamp=far_future), format="json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.data)

    def test_duplicate_id_returns_409_or_400(self):
        # concurrent race → IntegrityError → 409
        with patch.object(DeploymentSerializer, "save", side_effect=IntegrityError):
            resp = self.client.post("/deployments/", _valid_body(), format="json")
        self.assertEqual(resp.status_code, 409)

        # sequential duplicate → UniqueValidator → 400
        self.client.post("/deployments/", _valid_body(), format="json")
        resp = self.client.post("/deployments/", _valid_body(), format="json")
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# Update endpoint
# ---------------------------------------------------------------------------

class UpdateTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.dep = _make()

    def _put(self, dep_id=None, **overrides):
        dep_id = dep_id or self.dep.id
        payload = {
            "id": dep_id, "service": "auth-service", "status": "failed",
            "duration": 300, "timestamp": "2025-06-01T08:00:00Z", "commit_sha": "deadbeef",
        }
        payload.update(overrides)
        return self.client.put(f"/deployments/{dep_id}/", payload, format="json")

    def test_put_updates_data_and_invalidates_cache_with_log(self):
        self.client.get(f"/deployments/{self.dep.id}/")  # populate cache
        with self.assertLogs("deployments", level="INFO") as cm:
            resp = self._put()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["service"], "auth-service")
        self.assertTrue(any("cache invalidated" in line for line in cm.output))
        with self.assertNumQueries(1):
            self.client.get(f"/deployments/{self.dep.id}/")

    def test_put_errors_return_correct_status(self):
        self.assertEqual(
            self.client.put("/deployments/no-such-id/", _valid_body(), format="json").status_code,
            404,
        )
        resp = self._put(status="invalid-status")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.data)


# ---------------------------------------------------------------------------
# Request-ID middleware
# ---------------------------------------------------------------------------

class MiddlewareTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_request_id_header_generated_and_echoed(self):
        resp = self.client.get("/deployments/")
        self.assertIn("X-Request-ID", resp)

        resp = self.client.get("/deployments/", HTTP_X_REQUEST_ID="trace-abc-123")
        self.assertEqual(resp["X-Request-ID"], "trace-abc-123")
