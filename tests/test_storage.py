from pathlib import Path

from fraud_lens_gov.clustering import build_item_clusters
from fraud_lens_gov.sample_data import SAMPLE_ITEMS
from fraud_lens_gov.storage import Storage


def test_storage_persists_ingestion_runs_and_clusters(tmp_path: Path):
    storage = Storage(tmp_path / "fraudlens.sqlite")
    storage.init_schema()
    run = storage.start_ingestion_run("sample", {"records": len(SAMPLE_ITEMS)})
    written = storage.upsert_items(SAMPLE_ITEMS)
    storage.finish_ingestion_run(run.id, "success", len(SAMPLE_ITEMS), written)
    clusters, members = build_item_clusters(storage.list_items())
    storage.replace_item_clusters(clusters, members)

    summary = storage.dashboard_summary()

    assert summary["ingestion_runs"][0]["status"] == "success"
    assert summary["cluster_totals"]["clusters"] > 0
