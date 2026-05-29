from dataclasses import replace
from pathlib import Path

from fraud_lens_gov.anomalies import analyze_items
from fraud_lens_gov.clustering import build_cluster_index
from fraud_lens_gov.sample_data import SAMPLE_ITEMS
from fraud_lens_gov.storage import Storage


def test_storage_persists_ingestion_runs_and_clusters(tmp_path: Path):
    storage = Storage(tmp_path / "fraudlens.sqlite")
    storage.init_schema()
    run = storage.start_ingestion_run("sample", {"records": len(SAMPLE_ITEMS)})
    written = storage.upsert_items(SAMPLE_ITEMS)
    storage.finish_ingestion_run(run.id, "success", len(SAMPLE_ITEMS), written)
    clusters, members, neighbors = build_cluster_index(storage.list_items())
    storage.replace_item_clusters(clusters, members, neighbors)
    storage.replace_alerts(analyze_items(storage.list_items()))

    summary = storage.dashboard_summary()
    cluster_detail = storage.cluster_detail(clusters[0].id)
    alert = storage.list_alerts(limit=1)[0]
    alert_detail = storage.alert_detail(alert.id)

    assert summary["ingestion_runs"][0]["status"] == "success"
    assert summary["cluster_totals"]["clusters"] > 0
    assert summary["cluster_totals"]["neighbor_edges"] > 0
    assert cluster_detail
    assert cluster_detail["members"]
    assert alert_detail
    assert "neighbors" in alert_detail


def test_upsert_items_refreshes_normalized_fields(tmp_path: Path):
    storage = Storage(tmp_path / "fraudlens.sqlite")
    storage.init_schema()
    original = SAMPLE_ITEMS[0]
    enriched = replace(
        original,
        item_description="NOTEBOOK CORPORATIVO 14 POLEGADAS 32GB RAM",
        unit="UNIDADE",
        unit_price=5123,
        total_value=102460,
        source_payload={"descricaoItem": "Notebook corporativo 14 polegadas 32GB RAM"},
    )

    storage.upsert_items([original])
    storage.upsert_items([enriched])
    stored = next(item for item in storage.list_items() if item.id == original.id)

    assert stored.item_description == enriched.item_description
    assert stored.unit == "UNIDADE"
    assert stored.unit_price == 5123
    assert stored.source_payload["descricaoItem"] == "Notebook corporativo 14 polegadas 32GB RAM"


def test_storage_tracks_layers_and_pipeline_jobs(tmp_path: Path):
    storage = Storage(tmp_path / "fraudlens.sqlite")
    storage.init_schema()
    record = {
        "idContratacaoPNCP": "33781055000135-1-000463/2026",
        "idCompraItem": "ROW-1",
        "numeroItemPncp": 70,
        "dataResultadoPncp": "2026-05-01",
    }

    assert storage.upsert_bronze_records("compras_gov", [record], {"window": "test"}) == 1
    pending = storage.bronze_records_for_silver(source="compras_gov")
    job_id = storage.start_pipeline_job("Build Silver", "silver", {"limit": 1}, steps_total=2)
    storage.update_pipeline_job(job_id, current_step="record 1", steps_done=1, message="half")
    storage.finish_pipeline_job(job_id, "success")
    storage.upsert_items(SAMPLE_ITEMS)
    assert storage.replace_golden_items(SAMPLE_ITEMS) == len(SAMPLE_ITEMS)
    summary = storage.dashboard_summary()

    assert pending[0]["payload"]["numeroItemPncp"] == 70
    assert summary["layers"]["bronze"]["pending"] == 1
    assert summary["layers"]["silver"]["total"] == len(SAMPLE_ITEMS)
    assert summary["layers"]["golden"]["total"] == len(SAMPLE_ITEMS)
    assert summary["pipeline_jobs"][0]["progress"] == 100.0


def test_golden_materialization_can_process_only_stale_items(tmp_path: Path):
    storage = Storage(tmp_path / "fraudlens.sqlite")
    storage.init_schema()
    storage.upsert_items(SAMPLE_ITEMS[:2])

    assert storage.count_stale_golden_items() == 2
    assert storage.upsert_golden_items(SAMPLE_ITEMS[:2]) == 2
    assert storage.count_stale_golden_items() == 0

    changed = replace(
        SAMPLE_ITEMS[0],
        item_description="NOTEBOOK CORPORATIVO 14 POLEGADAS 64GB RAM",
        inserted_at="9999-01-01T00:00:00+00:00",
    )
    storage.upsert_items([changed])
    stale = storage.stale_golden_items()

    assert storage.count_stale_golden_items() == 1
    assert [item.id for item in stale] == [changed.id]
