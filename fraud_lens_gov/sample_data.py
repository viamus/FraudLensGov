from __future__ import annotations

from .models import ProcurementItem
from .normalization import normalize_text, stable_id


def _item(
    source_record_id: str,
    description: str,
    agency: str,
    agency_id: str,
    supplier: str,
    supplier_id: str,
    state: str,
    date: str,
    quantity: float,
    unit_price: float,
    modality: str = "PREGAO ELETRONICO",
) -> ProcurementItem:
    return ProcurementItem(
        id=stable_id("sample", source_record_id),
        source="sample",
        source_record_id=source_record_id,
        procurement_id=f"PROC-{source_record_id[:4]}",
        item_code=normalize_text(description)[:32],
        item_description=normalize_text(description),
        unit="UN",
        quantity=quantity,
        unit_price=unit_price,
        total_value=quantity * unit_price,
        currency="BRL",
        agency_name=normalize_text(agency),
        agency_id=agency_id,
        supplier_name=normalize_text(supplier),
        supplier_id=supplier_id,
        city="SAO PAULO",
        state=state,
        procurement_date=date,
        modality=modality,
        portal_url="https://pncp.gov.br/",
        source_payload={"sample": True},
    )


SAMPLE_ITEMS = [
    _item("SP-001", "Notebook corporativo 14 polegadas 16GB RAM", "Secretaria Municipal de Saude", "111", "Alpha Tecnologia Ltda", "1001", "SP", "2026-01-04", 20, 3900),
    _item("SP-002", "Notebook corporativo 14 polegadas 16GB RAM", "Secretaria Municipal de Educacao", "222", "Beta Digital Ltda", "1002", "SP", "2026-01-08", 15, 4050),
    _item("SP-003", "Notebook corporativo 14 polegadas 16GB RAM", "Secretaria Municipal de Obras", "333", "Gamma Solucoes Ltda", "1003", "SP", "2026-01-11", 18, 4200),
    _item("SP-004", "Notebook corporativo 14 polegadas 16GB RAM", "Secretaria Municipal de Saude", "111", "Alpha Tecnologia Ltda", "1001", "SP", "2026-01-18", 10, 10900),
    _item("SP-005", "Cesta basica familiar", "Secretaria Municipal de Assistencia", "444", "Comercial Boa Mesa", "2001", "SP", "2026-02-02", 1000, 118),
    _item("SP-006", "Cesta basica familiar", "Secretaria Municipal de Assistencia", "444", "Comercial Boa Mesa", "2001", "SP", "2026-02-08", 300, 121),
    _item("SP-007", "Cesta basica familiar", "Secretaria Municipal de Assistencia", "444", "Comercial Boa Mesa", "2001", "SP", "2026-02-14", 350, 119),
    _item("SP-008", "Cesta basica familiar", "Secretaria Municipal de Assistencia", "444", "Comercial Boa Mesa", "2001", "SP", "2026-02-20", 200, 120),
    _item("RJ-001", "Kit material escolar ensino fundamental", "Fundo Municipal de Educacao", "555", "Papelaria Central", "3001", "RJ", "2026-03-03", 600, 89),
    _item("RJ-002", "Kit material escolar ensino fundamental", "Fundo Municipal de Educacao", "555", "Papelaria Central", "3001", "RJ", "2026-03-07", 500, 91),
    _item("RJ-003", "Kit material escolar ensino fundamental", "Fundo Municipal de Educacao", "555", "Papelaria Central", "3001", "RJ", "2026-03-12", 450, 88),
    _item("RJ-004", "Kit material escolar ensino fundamental", "Fundo Municipal de Educacao", "555", "Papelaria Central", "3001", "RJ", "2026-03-22", 400, 90),
]
