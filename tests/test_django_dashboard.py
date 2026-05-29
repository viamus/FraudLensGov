from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fraudlensgov_site.settings")

import django
from django.test import Client, override_settings

from fraud_lens_gov.anomalies import analyze_items
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
    storage.replace_alerts(analyze_items(SAMPLE_ITEMS))


def test_django_dashboard_renders_operational_sections(tmp_path: Path):
    db_path = tmp_path / "fraudlens.sqlite"
    _seed_dashboard_db(db_path)

    with override_settings(FRAUDLENS_DB=str(db_path)):
        response = Client().get("/")

    assert response.status_code == 200
    html = response.content.decode("utf-8")
    assert "FraudLensGov" in html
    assert "Compras p\u00fablicas em revis\u00e3o" in html
    assert "Vis\u00e3o geral" in html


def test_django_dashboard_routes_are_separate_pages(tmp_path: Path):
    db_path = tmp_path / "fraudlens.sqlite"
    _seed_dashboard_db(db_path)
    client = Client()

    with override_settings(FRAUDLENS_DB=str(db_path)):
        pipeline = client.get("/pipeline")
        quality = client.get("/pipeline/qualidade")
        investigation = client.get("/investigacao")
        neighbors = client.get("/investigacao/vizinhos")
        normalization = client.get("/normalizacao")
        clusters = client.get("/normalizacao/clusters")
        operation = client.get("/operacao")
        ingestion = client.get("/operacao/ingestoes")

    assert pipeline.status_code == 200
    assert "Bronze / Silver / Golden" in pipeline.content.decode("utf-8")
    assert quality.status_code == 200
    assert "Bloqueios Golden" in quality.content.decode("utf-8")
    assert investigation.status_code == 200
    assert "Fila estat\u00edstica" in investigation.content.decode("utf-8")
    assert neighbors.status_code == 200
    assert "Pares para revis\u00e3o" in neighbors.content.decode("utf-8")
    assert normalization.status_code == 200
    assert "Categorias candidatas" in normalization.content.decode("utf-8")
    assert clusters.status_code == 200
    assert "Itens compar\u00e1veis" in clusters.content.decode("utf-8")
    assert operation.status_code == 200
    assert "Processamento" in operation.content.decode("utf-8")
    assert ingestion.status_code == 200
    assert "Execu\u00e7\u00f5es recentes" in ingestion.content.decode("utf-8")


def test_django_dashboard_pages_keep_one_primary_table(tmp_path: Path):
    db_path = tmp_path / "fraudlens.sqlite"
    _seed_dashboard_db(db_path)
    pages = [
        "/investigacao",
        "/investigacao/vizinhos",
        "/normalizacao",
        "/normalizacao/clusters",
        "/operacao",
        "/operacao/ingestoes",
    ]

    with override_settings(FRAUDLENS_DB=str(db_path)):
        for path in pages:
            response = Client().get(path)
            html = response.content.decode("utf-8")

            assert response.status_code == 200
            assert html.count('class="data-table') == 1


def test_django_knn_review_api_returns_pairs(tmp_path: Path):
    db_path = tmp_path / "fraudlens.sqlite"
    _seed_dashboard_db(db_path)

    with override_settings(FRAUDLENS_DB=str(db_path)):
        response = Client().get("/api/knn-review")

    assert response.status_code == 200
    payload = response.json()
    assert payload["pairs"]
    assert "price_ratio" in payload["pairs"][0]


def test_django_alert_detail_page_explains_outlier(tmp_path: Path):
    db_path = tmp_path / "fraudlens.sqlite"
    _seed_dashboard_db(db_path)
    storage = Storage(db_path)
    alert_id = storage.list_alerts(limit=1)[0].id

    with override_settings(FRAUDLENS_DB=str(db_path)):
        response = Client().get(f"/investigacao/alertas/{alert_id}")

    assert response.status_code == 200
    html = response.content.decode("utf-8")
    assert "Vizinhos usados no c\u00e1lculo" in html
    assert "Leitura audit\u00e1vel" in html
    assert "Pre\u00e7o normalizado" in html


def test_django_tables_render_filters_and_pagination(tmp_path: Path):
    db_path = tmp_path / "fraudlens.sqlite"
    _seed_dashboard_db(db_path)
    client = Client()

    with override_settings(FRAUDLENS_DB=str(db_path)):
        investigation = client.get("/investigacao", {"alerts_q": "notebook", "alerts_risk_type": "price_outlier"})
        normalization = client.get("/normalizacao")
        clusters = client.get("/normalizacao/clusters")
        operation = client.get("/operacao")
        ingestion = client.get("/operacao/ingestoes")

    assert investigation.status_code == 200
    investigation_html = investigation.content.decode("utf-8")
    assert 'name="alerts_q"' in investigation_html
    assert "table-pagination" in investigation_html
    assert "notebook" in investigation_html

    assert normalization.status_code == 200
    normalization_html = normalization.content.decode("utf-8")
    assert 'name="categories_q"' in normalization_html
    assert 'name="clusters_q"' not in normalization_html

    assert clusters.status_code == 200
    clusters_html = clusters.content.decode("utf-8")
    assert 'name="clusters_q"' in clusters_html

    assert operation.status_code == 200
    operation_html = operation.content.decode("utf-8")
    assert 'name="jobs_q"' in operation_html
    assert 'name="runs_q"' not in operation_html

    assert ingestion.status_code == 200
    ingestion_html = ingestion.content.decode("utf-8")
    assert 'name="runs_q"' in ingestion_html
    assert "Par\u00e2metros" in ingestion_html


def test_django_dashboard_guides_non_expert_reader(tmp_path: Path):
    db_path = tmp_path / "fraudlens.sqlite"
    _seed_dashboard_db(db_path)

    with override_settings(FRAUDLENS_DB=str(db_path)):
        response = Client().get("/normalizacao", {"categories_page": "2"})

    assert response.status_code == 200
    html = response.content.decode("utf-8")
    assert "Como o item foi categorizado?" in html
    assert "Dicion\u00e1rio r\u00e1pido" in html
    assert "Contexto e termos" in html
    assert "Grupo de itens parecidos o suficiente" in html
    assert "Categorias padronizam nomes" in html


def test_django_table_page_overflow_uses_last_available_page(tmp_path: Path):
    db_path = tmp_path / "fraudlens.sqlite"
    _seed_dashboard_db(db_path)

    with override_settings(FRAUDLENS_DB=str(db_path)):
        response = Client().get("/investigacao", {"alerts_page": "999"})

    assert response.status_code == 200
    html = response.content.decode("utf-8")
    assert "Sem alerta estat" not in html
    assert "999 /" not in html


def test_django_tables_sort_and_export_csv(tmp_path: Path):
    db_path = tmp_path / "fraudlens.sqlite"
    _seed_dashboard_db(db_path)

    with override_settings(FRAUDLENS_DB=str(db_path)):
        sorted_response = Client().get(
            "/investigacao",
            {"alerts_q": "notebook", "alerts_sort": "total_value", "alerts_dir": "desc"},
        )
        csv_response = Client().get(
            "/export/alerts",
            {"alerts_q": "notebook", "alerts_sort": "total_value", "alerts_dir": "desc"},
        )

    assert sorted_response.status_code == 200
    html = sorted_response.content.decode("utf-8")
    assert "alerts_sort=score" in html
    assert "/export/alerts?alerts_q=notebook&amp;alerts_sort=total_value&amp;alerts_dir=desc" in html

    assert csv_response.status_code == 200
    assert csv_response["Content-Type"].startswith("text/csv")
    assert "fraudlens-alerts.csv" in csv_response["Content-Disposition"]
    csv_text = csv_response.content.decode("utf-8-sig")
    assert "Severidade;Risco;Item" in csv_text
    assert "NOTEBOOK CORPORATIVO" in csv_text
