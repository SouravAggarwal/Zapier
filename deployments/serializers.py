from django.core.validators import RegexValidator
from django.utils.timezone import now, timedelta
from rest_framework import serializers
from .models import Deployment, SERVICE_CHOICES, STATUS_CHOICES


class DeploymentSerializer(serializers.ModelSerializer):
    """Serializes Deployment instances; field-level validators enforce all constraints."""

    duration = serializers.IntegerField(min_value=1, help_text="Duration in seconds")
    commit_sha = serializers.CharField(
        max_length=40,
        help_text="7–40 lowercase hex characters (short or full SHA)",
        validators=[RegexValidator(
            r"^[0-9a-f]{7,40}$",
            "commit_sha must be 7–40 lowercase hex characters.",
        )],
    )

    def validate_timestamp(self, value):
        if value > now() + timedelta(days=1):
            raise serializers.ValidationError(
                "timestamp cannot be in the future."
            )
        return value

    class Meta:
        model = Deployment
        fields = [
            "id", "service", "status", "duration", "timestamp",
            "commit_sha", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class DeploymentListResponseSerializer(serializers.Serializer):
    """Pagination envelope for GET /deployments/."""

    count = serializers.IntegerField()
    next_offset = serializers.IntegerField(allow_null=True)
    previous_offset = serializers.IntegerField(allow_null=True)
    results = DeploymentSerializer(many=True)


class DeploymentFilterSerializer(serializers.Serializer):
    """Validates all query parameters for GET /deployments/.
    """
    service = serializers.ChoiceField(
        choices=SERVICE_CHOICES, required=False, default=None, allow_null=True,
    )
    status = serializers.ChoiceField(
        choices=STATUS_CHOICES, required=False, default=None, allow_null=True,
    )
    timestamp_after = serializers.DateTimeField(
        required=False, default=None, allow_null=True,
        help_text="ISO 8601 — include deployments at or after this datetime",
    )
    timestamp_before = serializers.DateTimeField(
        required=False, default=None, allow_null=True,
        help_text="ISO 8601 — include deployments at or before this datetime",
    )
    limit = serializers.IntegerField(required=False, default=20, min_value=1, max_value=100)
    offset = serializers.IntegerField(required=False, default=0, min_value=0)
