import logging

from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime

from deployments.models import Deployment

logger = logging.getLogger("deployments")

SEED_EVENTS = [
    # billing-api — mixed statuses, varied durations
    {"id": "deploy_001", "service": "billing-api", "status": "success",
     "duration": 180, "timestamp": "2025-04-01T08:00:00Z", "commit_sha": "a1b2c3d"},
    {"id": "deploy_002", "service": "billing-api", "status": "failed",
     "duration": 320, "timestamp": "2025-04-05T12:30:00Z", "commit_sha": "b2c3d4e"},
    {"id": "deploy_003", "service": "billing-api", "status": "success",
     "duration": 210, "timestamp": "2025-04-10T09:15:00Z", "commit_sha": "c3d4e5f"},
    {"id": "deploy_004", "service": "billing-api", "status": "success",
     "duration": 195, "timestamp": "2025-04-18T14:00:00Z", "commit_sha": "d4e5f6a"},
    {"id": "deploy_005", "service": "billing-api", "status": "failed",
     "duration": 450, "timestamp": "2025-04-25T16:45:00Z", "commit_sha": "e5f6a7b"},
    {"id": "deploy_006", "service": "billing-api", "status": "success",
     "duration": 175, "timestamp": "2025-05-02T10:00:00Z", "commit_sha": "f6a7b8c"},
    {"id": "deploy_007", "service": "billing-api", "status": "success",
     "duration": 188, "timestamp": "2025-05-10T11:30:00Z", "commit_sha": "a7b8c9d"},
    {"id": "deploy_008", "service": "billing-api", "status": "running",
     "duration": 95, "timestamp": "2025-05-20T09:00:00Z", "commit_sha": "b8c9d0e"},
    {"id": "deploy_009", "service": "billing-api", "status": "success",
     "duration": 201, "timestamp": "2025-06-01T14:00:00Z", "commit_sha": "c9d0e1f"},

    # auth-service — mostly successful, one spike
    {"id": "deploy_010", "service": "auth-service", "status": "success",
     "duration": 90, "timestamp": "2025-04-03T07:00:00Z", "commit_sha": "d0e1f2a"},
    {"id": "deploy_011", "service": "auth-service", "status": "success",
     "duration": 85, "timestamp": "2025-04-12T08:30:00Z", "commit_sha": "e1f2a3b"},
    {"id": "deploy_012", "service": "auth-service", "status": "failed",
     "duration": 610, "timestamp": "2025-04-20T13:00:00Z", "commit_sha": "f2a3b4c"},
    {"id": "deploy_013", "service": "auth-service", "status": "success",
     "duration": 92, "timestamp": "2025-04-28T10:00:00Z", "commit_sha": "a3b4c5d"},
    {"id": "deploy_014", "service": "auth-service", "status": "success",
     "duration": 88, "timestamp": "2025-05-06T09:15:00Z", "commit_sha": "b4c5d6e"},
    {"id": "deploy_015", "service": "auth-service", "status": "success",
     "duration": 94, "timestamp": "2025-05-15T11:00:00Z", "commit_sha": "c5d6e7f"},
    {"id": "deploy_016", "service": "auth-service", "status": "running",
     "duration": 40, "timestamp": "2025-05-28T08:00:00Z", "commit_sha": "d6e7f8a"},
    {"id": "deploy_017", "service": "auth-service", "status": "success",
     "duration": 91, "timestamp": "2025-06-05T10:30:00Z", "commit_sha": "e7f8a9b"},

    # payment-processor — slower service, multiple failures
    {"id": "deploy_018", "service": "payment-processor", "status": "success",
     "duration": 540, "timestamp": "2025-04-02T09:00:00Z", "commit_sha": "f8a9b0c"},
    {"id": "deploy_019", "service": "payment-processor", "status": "failed",
     "duration": 720, "timestamp": "2025-04-08T15:30:00Z", "commit_sha": "a9b0c1d"},
    {"id": "deploy_020", "service": "payment-processor", "status": "failed",
     "duration": 680, "timestamp": "2025-04-14T12:00:00Z", "commit_sha": "b0c1d2e"},
    {"id": "deploy_021", "service": "payment-processor", "status": "success",
     "duration": 510, "timestamp": "2025-04-22T10:00:00Z", "commit_sha": "c1d2e3f"},
    {"id": "deploy_022", "service": "payment-processor", "status": "success",
     "duration": 495, "timestamp": "2025-05-01T09:00:00Z", "commit_sha": "d2e3f4a"},
    {"id": "deploy_023", "service": "payment-processor", "status": "success",
     "duration": 530, "timestamp": "2025-05-12T14:00:00Z", "commit_sha": "e3f4a5b"},
    {"id": "deploy_024", "service": "payment-processor", "status": "failed",
     "duration": 800, "timestamp": "2025-05-22T16:00:00Z", "commit_sha": "f4a5b6c"},
    {"id": "deploy_025", "service": "payment-processor", "status": "success",
     "duration": 520, "timestamp": "2025-06-02T11:00:00Z", "commit_sha": "a5b6c7d"},

    # notification-service — fast, reliable
    {"id": "deploy_026", "service": "notification-service", "status": "success",
     "duration": 60, "timestamp": "2025-04-04T08:00:00Z", "commit_sha": "b6c7d8e"},
    {"id": "deploy_027", "service": "notification-service", "status": "success",
     "duration": 55, "timestamp": "2025-04-15T09:00:00Z", "commit_sha": "c7d8e9f"},
    {"id": "deploy_028", "service": "notification-service", "status": "success",
     "duration": 62, "timestamp": "2025-04-26T10:30:00Z", "commit_sha": "d8e9f0a"},
    {"id": "deploy_029", "service": "notification-service", "status": "failed",
     "duration": 310, "timestamp": "2025-05-05T13:00:00Z", "commit_sha": "e9f0a1b"},
    {"id": "deploy_030", "service": "notification-service", "status": "success",
     "duration": 58, "timestamp": "2025-05-16T08:00:00Z", "commit_sha": "f0a1b2c"},
    {"id": "deploy_031", "service": "notification-service", "status": "success",
     "duration": 65, "timestamp": "2025-05-25T10:00:00Z", "commit_sha": "a1b2c3e"},
    {"id": "deploy_032", "service": "notification-service", "status": "running",
     "duration": 30, "timestamp": "2025-06-08T07:30:00Z", "commit_sha": "b2c3d4f"},
]


class Command(BaseCommand):
    help = "Seed database with mock deployment events"

    def handle(self, *args, **options):
        """Delete all existing records and insert seed data."""
        Deployment.objects.all().delete()
        created = 0
        for event in SEED_EVENTS:
            Deployment.objects.create(
                id=event["id"],
                service=event["service"],
                status=event["status"],
                duration=event["duration"],
                timestamp=parse_datetime(event["timestamp"]),
                commit_sha=event["commit_sha"],
            )
            created += 1
        logger.info("Seeded %d deployment events.", created)
