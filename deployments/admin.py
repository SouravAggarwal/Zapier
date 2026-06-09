from django.contrib import admin
from .models import Deployment


@admin.register(Deployment)
class DeploymentAdmin(admin.ModelAdmin):
    """Admin view for Deployment records."""

    list_display = ["id", "service", "status", "duration", "timestamp", "commit_sha"]
    list_filter = ["service", "status"]
    search_fields = ["id", "commit_sha"]
    ordering = ["-timestamp"]
