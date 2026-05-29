from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fraudlensgov_site.settings")

import django
from django.test import Client, override_settings

from fraud_lens_gov.clustering import build_cluster_index
from fraud_lens_gov.sample_data import SAMPLE_ITEMS
from fraud_lens_gov.storage import Storage


django.setup()


def _seed_dashboard_db(path: Path) -> None:
    storage = Storage(path)
    storage.init_schema()
    storage.upsert_items(SAMPLE_ITEMS)
    storage.replace_golden_items(SAMPLE_ITEMS)
    clusters, members, neighbors = build_cluster_index(SAMPLE_ITEMS)
    storage.replace_item_clusters(clusters, members, neighbors)


def test_django_dashboard_renders_operational_sections(tmp_path: Path):
    db_path = tmp_path / "fraudlens.sqlite"
    _seed_dashboard_db(db_path)

    with override_settings(FRAUDLENS_DB=str(db_path)):
        response = Client().get("/")

    assert response.status_code == 200
    html = response.content.decode("utf-8")
    assert "FraudLensGov" in html
    assert "Revisão KNN" in html
    assert "Bronze / Silver / Golden" in html


def test_django_knn_review_api_returns_pairs(tmp_path: Path):
    db_path = tmp_path / "fraudlens.sqlite"
    _seed_dashboard_db(db_path)

    with override_settings(FRAUDLENS_DB=str(db_path)):
        response = Client().get("/api/knn-review")

    assert response.status_code == 200
    payload = response.json()
    assert payload["pairs"]
    assert "price_ratio" in payload["pairs"][0]
