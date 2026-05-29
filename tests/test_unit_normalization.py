from dataclasses import replace

from fraud_lens_gov.item_quality import description_quality
from fraud_lens_gov.sample_data import SAMPLE_ITEMS
from fraud_lens_gov.unit_normalization import adjusted_price_for_unit, adjusted_unit_price, comparable_units, unit_family


def test_unit_family_and_adjusted_price_normalize_mass_units():
    item = replace(SAMPLE_ITEMS[0], unit="TONELADA", unit_price=3000)

    assert unit_family("TONELADA") == "mass"
    assert adjusted_unit_price(item) == 3


def test_embedded_package_measure_normalizes_to_base_volume():
    assert adjusted_price_for_unit("GARRAFA 2,00 L", 3.90) == 1.95
    assert round(adjusted_price_for_unit("COPO 200,00 ML", 35.80), 2) == 179.0
    assert adjusted_price_for_unit("EMBALAGEM 100,00 UN", 35.0) == 0.35


def test_comparable_units_reject_unit_vs_mass():
    left = replace(SAMPLE_ITEMS[0], unit="UNIDADE")
    right = replace(SAMPLE_ITEMS[1], unit="TONELADA")

    assert comparable_units(left, right) is False


def test_broad_predial_scope_requires_document_before_comparison():
    item = replace(
        SAMPLE_ITEMS[0],
        item_description="MANUTENCAO REFORMA PREDIAL",
        unit="UNIDADE",
        source_payload={"numeroItemPncp": 1},
    )

    quality = description_quality(item)

    assert quality["level"] == "broad_scope"
    assert quality["comparable"] is False


def test_generic_vehicle_part_with_unit_is_not_safe_benchmark():
    item = replace(
        SAMPLE_ITEMS[0],
        item_description="PECA MECANICA ELETRICA VEICULO AUTOMOTIVO",
        unit="UNIDADE",
        source_payload={"numeroItemPncp": 1},
    )

    quality = description_quality(item)

    assert quality["level"] == "broad_scope"
    assert quality["comparable"] is False


def test_service_convenio_with_unidade_requires_document():
    item = replace(
        SAMPLE_ITEMS[0],
        item_description="ASSISTENCIA MEDICA HOSPITALAR DOMICILIAR CONVENIO",
        unit="UNIDADE",
        source_payload={"numeroItemPncp": 1},
    )

    quality = description_quality(item)

    assert quality["level"] == "broad_scope"
    assert quality["comparable"] is False


def test_vehicle_maintenance_by_hour_requires_document_scope():
    item = replace(
        SAMPLE_ITEMS[0],
        item_description="MANUTENCAO DE VEICULOS LEVES E PESADOS",
        unit="HORA",
        source_payload={"numeroItemPncp": 1},
    )

    quality = description_quality(item)

    assert quality["level"] == "broad_scope"
    assert quality["comparable"] is False


def test_manipulated_formula_requires_structured_specification():
    item = replace(
        SAMPLE_ITEMS[0],
        item_description="MANIPULACAO DE FORMULAS MEDICAMENTOS COSMETICOS INSUMOS FARMACEUTICOS",
        item_code="1",
        unit="UNIDADE",
        source_payload={"numeroItemPncp": 1},
    )

    quality = description_quality(item)

    assert quality["level"] == "spec_required"
    assert quality["comparable"] is False


def test_food_service_bundle_is_broad_scope_without_reference_document():
    item = replace(
        SAMPLE_ITEMS[0],
        item_description="FORNECIMENTO DE REFEICOES LANCHES SALGADOS DOCES",
        unit="UNIDADE",
        source_payload={"numeroItemPncp": 1},
    )

    quality = description_quality(item)

    assert quality["level"] == "broad_scope"
    assert quality["comparable"] is False


def test_medical_device_family_requires_catalog_or_complement():
    item = replace(
        SAMPLE_ITEMS[0],
        item_description="SONDA TRATO DIGESTIVO",
        item_code="1",
        unit="UNIDADE",
        source_payload={"numeroItemPncp": 1},
    )

    quality = description_quality(item)

    assert quality["level"] == "spec_required"
    assert quality["comparable"] is False


def test_spec_required_item_becomes_comparable_with_catalog_metadata():
    item = replace(
        SAMPLE_ITEMS[0],
        item_description="SONDA TRATO DIGESTIVO",
        item_code="1",
        unit="UNIDADE",
        source_payload={"numeroItemPncp": 1, "catalogoCodigoItem": "CATMAT-123"},
    )

    quality = description_quality(item)

    assert quality["level"] == "usable"
    assert quality["comparable"] is True


def test_unit_service_repair_is_broad_scope_without_document():
    item = replace(
        SAMPLE_ITEMS[0],
        item_description="REPARO DE PNEU CAMARA DE AR",
        item_code="1",
        unit="UNIDADE",
        source_payload={"numeroItemPncp": 1},
    )

    quality = description_quality(item)

    assert quality["level"] == "broad_scope"
    assert quality["comparable"] is False


def test_training_service_is_broad_scope_without_document():
    item = replace(
        SAMPLE_ITEMS[0],
        item_description="TREINAMENTO QUALIFICACAO PROFISSIONAL",
        item_code="1",
        unit="UNIDADE",
        source_payload={"numeroItemPncp": 1},
    )

    quality = description_quality(item)

    assert quality["level"] == "broad_scope"
    assert quality["comparable"] is False


def test_medical_connector_requires_structured_specification():
    item = replace(
        SAMPLE_ITEMS[0],
        item_description="CONECTOR USO MEDICO",
        item_code="1",
        unit="UNIDADE",
        source_payload={"numeroItemPncp": 1},
    )

    quality = description_quality(item)

    assert quality["level"] == "spec_required"
    assert quality["comparable"] is False


def test_equipment_family_requires_structured_specification():
    item = replace(
        SAMPLE_ITEMS[0],
        item_description="APARELHO EQUIPAMENTO PARA CONDICIONAMENTO FISICO",
        item_code="1",
        unit="UNIDADE",
        source_payload={"numeroItemPncp": 1},
    )

    quality = description_quality(item)

    assert quality["level"] == "spec_required"
    assert quality["comparable"] is False
