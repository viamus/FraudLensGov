from __future__ import annotations

import re

from .models import ProcurementItem


GENERIC_TERMS = {
    "APARELHO",
    "EQUIPAMENTO",
    "LABORATORIO",
    "MATERIAL",
    "PECA",
    "REAGENTE",
    "SERVICO",
    "UNIDADE",
}


def description_quality(item: ProcurementItem) -> dict[str, object]:
    tokens = set(re.findall(r"[A-Z0-9]{2,}", item.item_description.upper()))
    generic_overlap = tokens & GENERIC_TERMS
    has_catalog = _has_catalog(item)
    has_complement = _has_complement(item)
    if item.item_description.startswith("ITEM PNCP"):
        return {
            "level": "missing",
            "comparable": False,
            "reason": "descricao ausente no resultado homologado",
        }
    if len(tokens) <= 3 and generic_overlap:
        return {
            "level": "generic",
            "comparable": has_catalog or has_complement,
            "reason": "descricao generica exige catalogo, complemento ou documento",
        }
    if len(tokens) <= 2:
        return {
            "level": "weak",
            "comparable": has_catalog or has_complement,
            "reason": "descricao curta exige catalogo, complemento ou documento",
        }
    return {
        "level": "usable",
        "comparable": True,
        "reason": "descricao suficiente para comparacao lexical inicial",
    }


def is_comparable(item: ProcurementItem) -> bool:
    return bool(description_quality(item)["comparable"])


def _has_catalog(item: ProcurementItem) -> bool:
    payload = item.source_payload or {}
    detail = payload.get("pncpItemDetail") if isinstance(payload.get("pncpItemDetail"), dict) else {}
    catalog_code = (
        payload.get("catalogoCodigoItem")
        or detail.get("catalogoCodigoItem")
        or payload.get("codigoItemCatalogo")
        or detail.get("codigoItemCatalogo")
    )
    if catalog_code:
        return True
    blocked_codes = {
        str(item.source_record_id or ""),
        str(payload.get("idCompraItem") or ""),
        str(payload.get("numeroItemPncp") or ""),
        str(detail.get("numeroItem") or ""),
    }
    return bool(item.item_code and item.item_code not in blocked_codes)


def _has_complement(item: ProcurementItem) -> bool:
    payload = item.source_payload or {}
    detail = payload.get("pncpItemDetail") if isinstance(payload.get("pncpItemDetail"), dict) else {}
    return bool(
        payload.get("informacaoComplementar")
        or detail.get("informacaoComplementar")
        or payload.get("descricaoDetalhada")
        or detail.get("descricaoDetalhada")
    )
