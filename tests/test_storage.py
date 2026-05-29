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
