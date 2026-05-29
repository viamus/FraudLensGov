from __future__ import annotations

from django.urls import path

from . import views


urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("pipeline", views.pipeline_page, name="pipeline"),
    path("investigacao", views.investigation_page, name="investigation"),
    path("investigacao/alertas/<str:alert_id>", views.alert_detail_page, name="alert-detail"),
    path("normalizacao", views.normalization_page, name="normalization"),
    path("operacao", views.operation_page, name="operation"),
    path("api/summary", views.summary_api, name="summary-api"),
    path("api/pipeline", views.pipeline_api, name="pipeline-api"),
    path("api/knn-review", views.knn_review_api, name="knn-review-api"),
    path("api/clusters/<str:cluster_id>", views.cluster_detail_api, name="cluster-detail-api"),
    path("api/alerts/<str:alert_id>", views.alert_detail_api, name="alert-detail-api"),
    path("api/items/<str:item_id>/neighbors", views.item_neighbors_api, name="item-neighbors-api"),
]
