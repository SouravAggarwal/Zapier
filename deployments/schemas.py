from .serializers import DeploymentListResponseSerializer, DeploymentSerializer
from rest_framework import serializers as s
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)

_ERROR = inline_serializer("Error", fields={"error": s.CharField()})

deployment_list_schema = extend_schema_view(
    get=extend_schema(
        operation_id="deployments_list",
        summary="List deployments",
        parameters=[
            OpenApiParameter("service", str, description="Filter by service name"),
            OpenApiParameter("status", str, description="Filter by status"),
            OpenApiParameter("timestamp_after", str, description="ISO 8601 — at or after"),
            OpenApiParameter("timestamp_before", str, description="ISO 8601 — at or before"),
            OpenApiParameter("limit", int, description="Page size (default 20, max 100)"),
            OpenApiParameter("offset", int, description="Pagination offset (default 0)"),
        ],
        responses={200: DeploymentListResponseSerializer, 400: _ERROR},
    ),
    post=extend_schema(
        operation_id="deployments_create",
        summary="Create a deployment",
        request=DeploymentSerializer,
        responses={201: DeploymentSerializer, 400: _ERROR, 409: _ERROR},
    ),
)

deployment_detail_schema = extend_schema_view(
    get=extend_schema(
        operation_id="deployments_retrieve",
        summary="Get a deployment",
        responses={200: DeploymentSerializer, 404: _ERROR},
    ),
    put=extend_schema(
        operation_id="deployments_update",
        summary="Update a deployment",
        request=DeploymentSerializer,
        responses={200: DeploymentSerializer, 400: _ERROR, 404: _ERROR},
    ),
)
