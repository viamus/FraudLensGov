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
        unit="NAO APLICAVEL",
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
    source_record_id = _first(raw, "idCompraItem", "id_compra_item", "idContratacaoPNCP", "id_contratacao_pncp") or stable_id(raw)
    quantity = as_float(_first(raw, "quantidadeHomologada", "quantidade_homologada"), 1.0)
    unit_price = as_float(_first(raw, "valorUnitarioHomologado", "valor_unitario_homologado"))
    total_value = as_float(_first(raw, "valorTotalHomologado", "valor_total_homologado"), quantity * unit_price)
    item_number = _first(raw, "numeroItemPncp", "numero_item", "numero_item_pncp")
    item_code = str(_first(raw, "idCompraItem", "id_compra_item", "numeroItemPncp", "numero_item", "numero_item_pncp") or "")
    procurement_id = str(_first(raw, "idContratacaoPNCP", "id_contratacao_pncp", "idCompra", "id_compra") or "")
    description = _first(raw, "descricaoItem", "descricao_item") or f"ITEM PNCP {item_number or item_code}"
    unit = _first(raw, "unidadeMedida", "unidade_medida") or "UN"
    item_catalog_code = _first(raw, "catalogoCodigoItem", "catalogo_codigo_item")
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
        agency_name=normalize_text(_first(raw, "unidadeOrgaoCodigoUnidade", "unidade_orgao_codigo_unidade", "orgaoEntidadeCnpj", "orgao_entidade_cnpj")),
        agency_id=str(_first(raw, "orgaoEntidadeCnpj", "orgao_entidade_cnpj", "unidadeOrgaoCodigoUnidade", "unidade_orgao_codigo_unidade") or ""),
        supplier_name=normalize_text(_first(raw, "nomeRazaoSocialFornecedor", "nome_razao_social_fornecedor")),
        supplier_id=str(_first(raw, "niFornecedor", "ni_fornecedor") or ""),
        city="",
        state=normalize_text(_first(raw, "unidadeOrgaoUfSigla", "unidade_orgao_uf_sigla")),
        procurement_date=str(_first(raw, "dataResultadoPncp", "data_resultado", "data_resultado_pncp", "dataInclusaoPncp", "data_inclusao", "data_inclusao_pncp") or "")[:10],
        modality="",
        portal_url=f"https://pncp.gov.br/app/editais/{procurement_id}" if procurement_id else "",
        source_payload=raw,
    )


def _first(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None
