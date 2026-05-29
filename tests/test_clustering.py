from dataclasses import replace

from fraud_lens_gov.clustering import build_cluster_index, build_item_clusters, nearest_neighbors
from fraud_lens_gov.sample_data import SAMPLE_ITEMS


def test_nearest_neighbors_finds_similar_procurement_items():
    neighbors = nearest_neighbors(SAMPLE_ITEMS, k=3, min_similarity=0.42)
    notebook = next(item for item in SAMPLE_ITEMS if item.source_record_id == "SP-004")

    assert neighbors[notebook.id]


def test_build_item_clusters_groups_sample_items():
    clusters, members = build_item_clusters(SAMPLE_ITEMS, k=4, min_similarity=0.42)

    assert clusters
    assert members
    assert max(cluster.item_count for cluster in clusters) >= 4


def test_build_cluster_index_returns_ranked_neighbors():
    clusters, members, neighbors = build_cluster_index(SAMPLE_ITEMS, k=4, min_similarity=0.42)

    assert clusters
    assert members
    assert neighbors
    assert min(neighbor.rank for neighbor in neighbors) == 1


def test_nearest_neighbors_uses_indexed_candidates_for_large_sets():
    items = [
        replace(item, id=f"{item.id}-{batch}", source_record_id=f"{item.source_record_id}-{batch}")
        for batch in range(80)
        for item in SAMPLE_ITEMS
    ]

    neighbors = nearest_neighbors(items, k=3, min_similarity=0.42)

    assert any(rows for rows in neighbors.values())


def test_cluster_price_statistics_use_normalized_unit_price():
    left = replace(
        SAMPLE_ITEMS[0],
        id="mass-kg",
        source_record_id="mass-kg",
        item_description="FARINHA TRIGO TIPO UM",
        unit="KG",
        unit_price=3,
        total_value=300,
        source_payload={"catalogoCodigoItem": "CATMAT-FARINHA"},
    )
    right = replace(
        SAMPLE_ITEMS[0],
        id="mass-ton",
        source_record_id="mass-ton",
        item_description="FARINHA TRIGO TIPO UM",
        unit="TONELADA",
        unit_price=3000,
        total_value=3000,
        source_payload={"catalogoCodigoItem": "CATMAT-FARINHA"},
    )

    clusters, _, _ = build_cluster_index([left, right], k=1, min_similarity=0.42)

    assert clusters[0].avg_unit_price == 3
    assert clusters[0].min_unit_price == 3
    assert clusters[0].max_unit_price == 3
