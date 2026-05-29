from dataclasses import replace

from fraud_lens_gov.anomalies import analyze_items
from fraud_lens_gov.clustering import build_cluster_index, build_item_clusters, nearest_neighbors
from fraud_lens_gov.models import ProcurementItem
from fraud_lens_gov.normalization import stable_id
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


def test_nearest_neighbors_rejects_context_only_dental_matches():
    target = _semantic_item("TORNO - USO ODONTOLOGICO", 906.52, "torno")
    unrelated = [
        _semantic_item("ESCOVA DE ROBSON USO ODONTOLOGICO", 2.4, "escova"),
        _semantic_item("LIGA - USO ODONTOLOGICO", 397.98, "liga"),
        _semantic_item("PONTA MONTADA USO ODONTOLOGICO", 32.18, "ponta"),
    ]

    neighbors = nearest_neighbors([target, *unrelated], k=4, min_similarity=0.1)

    assert neighbors[target.id] == []


def test_nearest_neighbors_keeps_same_semantic_anchor():
    left = _semantic_item("ESCOVA DE ROBSON USO ODONTOLOGICO", 2.4, "escova-sp")
    right = _semantic_item("ESCOVA ROBSON ODONTOLOGICA", 2.9, "escova-ba")

    neighbors = nearest_neighbors([left, right], k=1, min_similarity=0.42)

    assert neighbors[left.id][0][0] == right.id


def test_nearest_neighbors_rejects_accessory_as_equipment_neighbor():
    machine = _semantic_item("MAQUINA COSTURA TECIDO", 8699.99, "maquina")
    accessory = _semantic_item("AGULHA MAQUINA COSTURA", 8.19, "agulha")
    same_machine = _semantic_item("MAQUINA COSTURA INDUSTRIAL", 2693.65, "maquina-industrial")

    neighbors = nearest_neighbors([machine, accessory, same_machine], k=2, min_similarity=0.1)

    neighbor_ids = {neighbor_id for neighbor_id, _ in neighbors[machine.id]}
    assert same_machine.id in neighbor_ids
    assert accessory.id not in neighbor_ids


def test_price_outlier_ignores_context_only_dental_neighbors():
    items = [
        _semantic_item("TORNO - USO ODONTOLOGICO", 906.52, "torno"),
        _semantic_item("ESCOVA DE ROBSON USO ODONTOLOGICO", 2.4, "escova-1"),
        _semantic_item("ESCOVA DE ROBSON USO ODONTOLOGICO", 0.91, "escova-2"),
        _semantic_item("LIGA - USO ODONTOLOGICO", 397.98, "liga"),
        _semantic_item("PONTA MONTADA USO ODONTOLOGICO", 32.18, "ponta"),
    ]

    assert [alert for alert in analyze_items(items) if alert.risk_type == "price_outlier"] == []


def _semantic_item(description: str, price: float, suffix: str) -> ProcurementItem:
    return ProcurementItem(
        id=stable_id("semantic-test", suffix),
        source="compras_gov",
        source_record_id=f"SEM-{suffix}",
        procurement_id="PROC-SEMANTIC",
        item_code=f"CODE-{suffix}",
        item_description=description,
        unit="UNIDADE",
        quantity=1,
        unit_price=price,
        total_value=price,
        currency="BRL",
        agency_name="ORGAO",
        agency_id="1",
        supplier_name=f"FORNECEDOR {suffix}",
        supplier_id=suffix,
        city="",
        state="SP",
        procurement_date="2026-05-01",
        modality="",
        source_payload={"id_compra_item": f"CODE-{suffix}"},
    )
