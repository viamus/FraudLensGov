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
