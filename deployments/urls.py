from django.urls import path
from .views import DeploymentDetailView, DeploymentListView

urlpatterns = [
    path("deployments/", DeploymentListView.as_view(), name="deployment-list"),
    path(
        "deployments/<str:deployment_id>/",
        DeploymentDetailView.as_view(),
        name="deployment-detail",
    ),
]
