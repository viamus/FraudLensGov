from __future__ import annotations

import hashlib
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

from .models import ProcurementItem


_SPACE_RE = re.compile(r"\s+")


def stable_id(*parts: Any) -> str:
    raw = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return _SPACE_RE.sub(" ", text).strip().upper()


def as_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(Decimal(str(value).replace(",", ".")))
    except (InvalidOperation, ValueError):
        return default


def from_pncp_notice(raw: dict[str, Any]) -> ProcurementItem:
    source_record_id = raw.get("numeroControlePNCP") or stable_id(raw.get("orgaoEntidade"), raw.get("numeroCompra"))
    orgao = raw.get("orgaoEntidade") or {}
    unidade = raw.get("unidadeOrgao") or {}
    description = raw.get("objetoCompra") or raw.get("informacaoComplementar") or "Contratacao sem descricao"
    total_value = as_float(raw.get("valorTotalEstimado") or raw.get("valorTotalHomologado"))
    quantity = 1.0
    unit_price = total_value
    procurement_date = (raw.get("dataPublicacaoPncp") or raw.get("dataInclusao") or "")[:10]
    return ProcurementItem(
        id=stable_id("pncp", source_record_id),
        source="pncp",
        source_record_id=str(source_record_id),
        procurement_id=str(source_record_id),
        item_code=str(raw.get("numeroCompra") or source_record_id),
        item_description=normalize_text(description),
        unit="CONTRATACAO",
        quantity=quantity,
        unit_price=unit_price,
        total_value=total_value,
        currency="BRL",
        agency_name=normalize_text(orgao.get("razaoSocial") or unidade.get("nomeUnidade")),
        agency_id=str(orgao.get("cnpj") or unidade.get("codigoUnidade") or ""),
        supplier_name="",
        supplier_id="",
        city=normalize_text(unidade.get("municipioNome")),
        state=normalize_text(unidade.get("ufSigla")),
        procurement_date=procurement_date,
        modality=normalize_text((raw.get("modalidadeNome") or raw.get("modalidadeIdPncp") or "")),
        portal_url=f"https://pncp.gov.br/app/editais/{source_record_id}" if source_record_id else "",
        source_payload=raw,
    )


def from_compras_award(raw: dict[str, Any]) -> ProcurementItem:
    source_record_id = raw.get("idCompraItem") or raw.get("idContratacaoPNCP") or stable_id(raw)
    quantity = as_float(raw.get("quantidadeHomologada"), 1.0)
    unit_price = as_float(raw.get("valorUnitarioHomologado"))
    total_value = as_float(raw.get("valorTotalHomologado"), quantity * unit_price)
    item_code = str(raw.get("idCompraItem") or raw.get("numeroItemPncp") or "")
    procurement_id = str(raw.get("idContratacaoPNCP") or raw.get("idCompra") or "")
    description = raw.get("descricaoItem") or f"ITEM PNCP {raw.get('numeroItemPncp') or item_code}"
    unit = raw.get("unidadeMedida") or "UN"
    item_catalog_code = raw.get("catalogoCodigoItem")
    return ProcurementItem(
        id=stable_id("compras_gov", source_record_id),
        source="compras_gov",
        source_record_id=str(source_record_id),
        procurement_id=procurement_id,
        item_code=str(item_catalog_code or item_code),
        item_description=normalize_text(description),
        unit=normalize_text(unit),
        quantity=quantity,
        unit_price=unit_price,
        total_value=total_value,
        currency="BRL",
        agency_name=normalize_text(raw.get("unidadeOrgaoCodigoUnidade") or raw.get("orgaoEntidadeCnpj")),
        agency_id=str(raw.get("orgaoEntidadeCnpj") or raw.get("unidadeOrgaoCodigoUnidade") or ""),
        supplier_name=normalize_text(raw.get("nomeRazaoSocialFornecedor")),
        supplier_id=str(raw.get("niFornecedor") or ""),
        city="",
        state=normalize_text(raw.get("unidadeOrgaoUfSigla")),
        procurement_date=(raw.get("dataResultadoPncp") or raw.get("dataInclusaoPncp") or "")[:10],
        modality="",
        portal_url=f"https://pncp.gov.br/app/editais/{procurement_id}" if procurement_id else "",
        source_payload=raw,
    )
