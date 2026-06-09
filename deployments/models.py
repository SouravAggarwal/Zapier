from django.db import models

SERVICE_CHOICES = [
    ("billing-api", "Billing API"),
    ("auth-service", "Auth Service"),
    ("payment-processor", "Payment Processor"),
    ("notification-service", "Notification Service"),
]

STATUS_CHOICES = [
    ("success", "Success"),
    ("failed", "Failed"),
    ("running", "Running"),
]


class Deployment(models.Model):
    """Records a single deployment event for a service."""

    id = models.CharField(max_length=50, primary_key=True)
    service = models.CharField(max_length=100, db_index=True, choices=SERVICE_CHOICES)
    status = models.CharField(max_length=20, db_index=True, choices=STATUS_CHOICES)
    duration = models.IntegerField(help_text="Duration in seconds")
    timestamp = models.DateTimeField(db_index=True)
    commit_sha = models.CharField(max_length=40, help_text="7–40 hex chars (short or full SHA)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.id} ({self.service} — {self.status})"
