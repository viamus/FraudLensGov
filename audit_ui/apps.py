from __future__ import annotations

from django.apps import AppConfig


class AuditUiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "audit_ui"
