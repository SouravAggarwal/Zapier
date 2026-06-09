import logging
from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from .services.cache import deployment_cache
from .models import Deployment
from .schemas import deployment_detail_schema, deployment_list_schema
from .serializers import DeploymentFilterSerializer, DeploymentSerializer

logger = logging.getLogger("deployments")


@deployment_list_schema
class DeploymentListView(APIView):
    """Handle deployment listing with filtering/pagination and deployment creation."""

    def get(self, request):
        """List deployments with optional filtering and offset-based pagination."""
        filter_serializer = DeploymentFilterSerializer(data=request.query_params)

        if not filter_serializer.is_valid():
            logger.warning("Invalid list filters: %s", filter_serializer.errors)
            return Response({"error": filter_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        filters = filter_serializer.validated_data
        queryset = Deployment.objects.order_by("-id")

        if filters.get("service"):
            queryset = queryset.filter(service=filters["service"])

        if filters.get("status"):
            queryset = queryset.filter(status=filters["status"])

        if filters.get("timestamp_after"):
            queryset = queryset.filter(timestamp__gte=filters["timestamp_after"])

        if filters.get("timestamp_before"):
            queryset = queryset.filter(timestamp__lte=filters["timestamp_before"])

        count = queryset.count()
        offset = filters["offset"]
        limit = filters["limit"]
        response_serializer = DeploymentSerializer(queryset[offset:offset + limit], many=True)

        logger.info(
            "deployment_list service=%s status=%s limit=%d offset=%d count=%d",
            filters.get("service"), filters.get("status"), limit, offset, count,
        )
        return Response({
            "count": count,
            "next_offset": offset + limit if offset + limit < count else None,
            "previous_offset": max(0, offset - limit) if offset > 0 else None,
            "results": response_serializer.data,
        })

    def post(self, request):
        """Create a deployment. IntegrityError on concurrent duplicate ID → 409."""
        serializer = DeploymentSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning("Deployment create failed: %s", serializer.errors)
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        try:
            serializer.save()
        except IntegrityError:
            logger.warning(
                "Duplicate deployment id=%s (race condition)",
                serializer.validated_data.get("id"),
            )
            return Response(
                {"error": "A deployment with this ID already exists."},
                status=status.HTTP_409_CONFLICT,
            )

        logger.info(
            "Deployment created id=%s service=%s",
            serializer.data["id"],
            serializer.data["service"],
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)


@deployment_detail_schema
class DeploymentDetailView(APIView):
    """Retrieve (GET) or fully update (PUT) a single deployment by ID."""

    def get(self, request, deployment_id):
        """Serve from in-memory cache; fall back to DB on miss."""
        cached = deployment_cache.get(deployment_id)
        if cached is not None:
            return Response(cached)

        try:
            deployment = Deployment.objects.get(pk=deployment_id)
        except Deployment.DoesNotExist:
            logger.warning("Deployment not found id=%s", deployment_id)
            return Response(
                {"error": f"No deployment found with id '{deployment_id}'."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = DeploymentSerializer(deployment)
        deployment_cache.set(deployment_id, serializer.data)
        logger.info(
            "deployment_detail id=%s (from DB, cached for %ds)",
            deployment_id,
            settings.DEPLOYMENT_CACHE_TTL,
        )
        return Response(serializer.data)

    def put(self, request, deployment_id):
        """Fully update a deployment object."""
        try:
            with transaction.atomic():
                deployment = Deployment.objects.select_for_update().get(pk=deployment_id)
                serializer = DeploymentSerializer(deployment, data=request.data)

                if not serializer.is_valid():
                    logger.warning(
                        "Deployment update failed id=%s errors=%s",
                        deployment_id,
                        serializer.errors,
                    )
                    return Response(
                        {"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
                    )

                serializer.save()
                deployment_cache.invalidate(deployment_id)
                logger.info("Deployment updated id=%s, cache invalidated", deployment_id)
                return Response(serializer.data)

        except Deployment.DoesNotExist:
            logger.warning("Deployment PUT not found id=%s", deployment_id)
            return Response(
                {"error": f"No deployment found with id '{deployment_id}'."},
                status=status.HTTP_404_NOT_FOUND,
            )
