from fraud_lens_gov.anomalies import analyze_items
from fraud_lens_gov.clustering import build_cluster_index
from fraud_lens_gov.item_quality import description_quality
from fraud_lens_gov.models import ProcurementItem
from fraud_lens_gov.normalization import stable_id


def _item(description: str, price: float, suffix: str, payload: dict[str, object] | None = None) -> ProcurementItem:
    return ProcurementItem(
        id=stable_id("quality", suffix),
        source="compras_gov",
        source_record_id=f"ROW-{suffix}",
        procurement_id="33781055000135-1-000463/2026",
        item_code="70",
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
        source_payload=payload or {"numeroItemPncp": 70},
    )


def test_generic_lab_equipment_description_is_not_comparable_without_catalog():
    item = _item("PECA EQUIPAMENTO LABORATORIO", 100, "1")

    quality = description_quality(item)

    assert quality["level"] == "generic"
    assert quality["comparable"] is False


def test_generic_description_becomes_comparable_with_catalog_metadata():
    item = _item(
        "PECA EQUIPAMENTO LABORATORIO",
        100,
        "1",
        {"numeroItemPncp": 70, "catalogoCodigoItem": "CATMAT-123"},
    )

    quality = description_quality(item)

    assert quality["level"] == "generic"
    assert quality["comparable"] is True


def test_clustering_excludes_generic_items_without_catalog():
    items = [
        _item("PECA EQUIPAMENTO LABORATORIO", 100, "1"),
        _item("PECA EQUIPAMENTO LABORATORIO", 1000000, "2"),
    ]

    clusters, members, neighbors = build_cluster_index(items, min_similarity=0.1)

    assert clusters == []
    assert members == []
    assert neighbors == []


def test_anomaly_detection_excludes_generic_items_without_catalog():
    items = [
        _item("PECA EQUIPAMENTO LABORATORIO", 100, "1"),
        _item("PECA EQUIPAMENTO LABORATORIO", 110, "2"),
        _item("PECA EQUIPAMENTO LABORATORIO", 95, "3"),
        _item("PECA EQUIPAMENTO LABORATORIO", 1000000, "4"),
    ]

    assert analyze_items(items) == []
