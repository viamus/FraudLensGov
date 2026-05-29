from __future__ import annotations

import re

from .candidate_index import meaningful_item_code
from .models import ProcurementItem


MASS_UNITS = {"KG", "G", "GRAMA", "GRAMAS", "TON", "TONELADA", "TONELADAS"}
VOLUME_UNITS = {"L", "LT", "LITRO", "LITROS", "ML", "MILILITRO", "MILILITROS"}
COUNT_UNITS = {"UN", "UND", "UNIDADE", "UNIDADES", "PC", "PECA", "PECAS"}
TIME_UNITS = {"HORA", "HORAS", "MES", "MESES", "DIA", "DIAS", "ANO", "ANOS"}
PACKAGE_UNITS = {"CAIXA", "CX", "PACOTE", "PCT", "ROLO", "FRASCO", "GALAO", "SACO", "BALDE", "KIT"}
SERVICE_UNITS = {"SERVICO", "SERVICOS", "POSTO", "DIARIA", "EVENTO", "CONTRATACAO", "NAO APLICAVEL"}

CONVERSION_TO_BASE = {
    "UN": ("count", 1.0),
    "UND": ("count", 1.0),
    "UNIDADE": ("count", 1.0),
    "UNIDADES": ("count", 1.0),
    "G": ("mass", 0.001),
    "GRAMA": ("mass", 0.001),
    "GRAMAS": ("mass", 0.001),
    "KG": ("mass", 1.0),
    "TON": ("mass", 1000.0),
    "TONELADA": ("mass", 1000.0),
    "TONELADAS": ("mass", 1000.0),
    "ML": ("volume", 0.001),
    "MILILITRO": ("volume", 0.001),
    "MILILITROS": ("volume", 0.001),
    "L": ("volume", 1.0),
    "LT": ("volume", 1.0),
    "LITRO": ("volume", 1.0),
    "LITROS": ("volume", 1.0),
}

BROAD_SCOPE_TOKENS = {
    "ASSISTENCIA",
    "CONVENIO",
    "CONSTRUCAO",
    "CONFECCAO",
    "ENGENHARIA",
    "EDICAO",
    "EXPLORACAO",
    "FORNECIMENTO",
    "GRAFICO",
    "HOTEIS",
    "HOSPITALAR",
    "INSTALACAO",
    "LOCACAO",
    "MANUTENCAO",
    "MONTAGEM",
    "OBRA",
    "OBRAS",
    "POUSADAS",
    "PREDIAL",
    "REALIZACAO",
    "REFEICOES",
    "REMOCAO",
    "REPARO",
    "REFORMA",
    "SERVICO",
    "SERVICOS",
    "SHOWS",
    "TRANSPORTE",
    "TREINAMENTO",
}

BROAD_PART_TOKENS = {
    "ACESSORIO",
    "ACESSORIOS",
    "APARELHO",
    "AUTOMOTIVO",
    "ELETRICA",
    "MECANICA",
    "PECA",
    "PECAS",
    "VEICULO",
    "VEICULOS",
}
BROAD_EVENT_TOKENS = {"REALIZACAO", "SHOWS", "CONCURSOS", "ARTISTICOS", "CULTURAIS"}
FOOD_SERVICE_TOKENS = {"ALIMENTACAO", "DOCES", "LANCHES", "REFEICAO", "REFEICOES", "SALGADOS"}
FORMULA_TOKENS = {"COSMETICOS", "FARMACEUTICOS", "FORMULA", "FORMULAS", "INSUMOS", "MANIPULACAO", "MEDICAMENTOS"}
SERVICE_ACTION_TOKENS = {
    "AVIAMENTO",
    "BORDADO",
    "CONFECCAO",
    "DESMONTAGEM",
    "EDICAO",
    "ENCOMENDAS",
    "IMPRESSAO",
    "INSTALACAO",
    "QUALIFICACAO",
    "MANUTENCAO",
    "MONTAGEM",
    "PROFISSIONAL",
    "REMOCAO",
    "REPARO",
    "TRANSPORTE",
    "TREINAMENTO",
}
SPEC_REQUIRED_PRODUCT_TOKENS = {
    "ACESSORIO",
    "ACESSORIOS",
    "ACABAMENTO",
    "AGULHADO",
    "APARELHO",
    "BROCA",
    "CAMERA",
    "CATETER",
    "CONECTOR",
    "EQUIPO",
    "EQUIPAMENTO",
    "IMPLANTE",
    "KIT",
    "MATERIAL",
    "ORTESE",
    "PROTESE",
    "SUTURA",
    "VALVULA",
    "SONDA",
}
MEDICAL_CONTEXT_TOKENS = {"HOSPITALAR", "MEDICA", "MEDICO", "ODONTOLOGICO"}
EMBEDDED_MEASURE_RE = re.compile(
    r"(?P<amount>\d+(?:[,.]\d+)?)\s*"
    r"(?P<unit>KG|G|GRAMA|GRAMAS|TON|TONELADA|TONELADAS|L|LT|LITRO|LITROS|ML|MILILITRO|MILILITROS|UN|UND|UNIDADE|UNIDADES)\b"
)


def unit_family(unit: str) -> str:
    tokens = _unit_tokens(unit)
    if tokens & MASS_UNITS:
        return "mass"
    if tokens & VOLUME_UNITS:
        return "volume"
    if tokens & TIME_UNITS:
        return "time"
    if tokens & PACKAGE_UNITS:
        return "package"
    if tokens & SERVICE_UNITS:
        return "service"
    if tokens & COUNT_UNITS:
        return "count"
    return "unknown"


def comparable_units(left: ProcurementItem, right: ProcurementItem) -> bool:
    left_family = unit_family(left.unit)
    right_family = unit_family(right.unit)
    if not left_family or not right_family or "unknown" in {left_family, right_family}:
        return _normalized_unit(left.unit) == _normalized_unit(right.unit)
    if left_family != right_family:
        return False
    if left_family in {"package", "service"}:
        return _normalized_unit(left.unit) == _normalized_unit(right.unit)
    return True


def adjusted_unit_price(item: ProcurementItem) -> float:
    return adjusted_price_for_unit(item.unit, item.unit_price)


def adjusted_price_for_unit(unit: str, unit_price: float) -> float:
    embedded_quantity = _embedded_base_quantity(unit)
    if embedded_quantity > 0:
        return unit_price / embedded_quantity
    tokens = _unit_tokens(unit)
    for token in tokens:
        conversion = CONVERSION_TO_BASE.get(token)
        if conversion:
            _, multiplier = conversion
            if multiplier > 0:
                return unit_price / multiplier
    return unit_price


def broad_scope_requires_document(item: ProcurementItem) -> bool:
    tokens = _description_tokens(item)
    if len(tokens) <= 4 and tokens & BROAD_SCOPE_TOKENS:
        return True
    if "UNIDADE" in _unit_tokens(item.unit) and tokens & BROAD_SCOPE_TOKENS:
        return True
    if "UNIDADE" in _unit_tokens(item.unit) and len(tokens & BROAD_PART_TOKENS) >= 2:
        return True
    if len(tokens & BROAD_EVENT_TOKENS) >= 2:
        return True
    if "MANUTENCAO" in tokens and bool(tokens & {"VEICULO", "VEICULOS", "AUTOMOTIVO"}):
        return True
    if tokens & SERVICE_ACTION_TOKENS and unit_family(item.unit) in {"count", "service"}:
        return True
    if "FORNECIMENTO" in tokens and tokens & FOOD_SERVICE_TOKENS:
        return True
    if "EXPLORACAO" in tokens and tokens & {"COMERCIAL", "HOTEIS", "POUSADAS"}:
        return True
    unit = unit_family(item.unit)
    return unit == "service" and len(tokens & BROAD_SCOPE_TOKENS) >= 2


def requires_structured_specification(item: ProcurementItem) -> bool:
    tokens = _description_tokens(item)
    if not tokens:
        return True
    if "MANIPULACAO" in tokens and len(tokens & FORMULA_TOKENS) >= 2:
        return True
    if len(tokens & FOOD_SERVICE_TOKENS) >= 2:
        return True
    if tokens & MEDICAL_CONTEXT_TOKENS and tokens & SPEC_REQUIRED_PRODUCT_TOKENS:
        return True
    if len(tokens & {"FIO", "SUTURA", "AGULHADO"}) >= 2:
        return True
    if tokens & {"APARELHO", "EQUIPAMENTO"} and len(tokens) <= 6:
        return True
    if "PROTETOR" in tokens and bool(tokens & {"SURTO", "TRANSITORIO"}):
        return True
    if tokens & {"ACABAMENTO", "VALVULA"} and len(tokens) <= 5:
        return True
    if tokens & {"PECA", "PECAS", "ACESSORIO", "ACESSORIOS"} and tokens & {
        "APARELHO",
        "AUTOMOTIVO",
        "CONDICIONADO",
        "ELETRICA",
        "MECANICA",
        "VEICULO",
        "VEICULOS",
    }:
        return True
    if len(tokens) <= 4 and tokens & SPEC_REQUIRED_PRODUCT_TOKENS:
        return True
    return False


def is_price_benchmarkable(item: ProcurementItem) -> bool:
    if adjusted_unit_price(item) <= 0.05:
        return False
    if broad_scope_requires_document(item) and not _has_detail_metadata(item):
        return False
    if requires_structured_specification(item) and not _has_specific_metadata(item):
        return False
    return True


def _unit_tokens(unit: str) -> set[str]:
    return set(re.findall(r"[A-Z0-9]+", _normalized_unit(unit)))


def _embedded_base_quantity(unit: str) -> float:
    normalized = _normalized_unit(unit).replace(",", ".")
    match = EMBEDDED_MEASURE_RE.search(normalized)
    if not match:
        return 0.0
    amount = float(match.group("amount"))
    conversion = CONVERSION_TO_BASE.get(match.group("unit"))
    if not conversion:
        return 0.0
    _, multiplier = conversion
    return amount * multiplier


def _description_tokens(item: ProcurementItem) -> set[str]:
    return set(re.findall(r"[A-Z0-9]{2,}", item.item_description.upper()))


def _has_specific_metadata(item: ProcurementItem) -> bool:
    return _has_detail_metadata(item) or _has_catalog_metadata(item) or bool(meaningful_item_code(item))


def _has_detail_metadata(item: ProcurementItem) -> bool:
    payload = item.source_payload or {}
    detail = payload.get("pncpItemDetail") if isinstance(payload.get("pncpItemDetail"), dict) else {}
    return bool(
        payload.get("informacaoComplementar")
        or detail.get("informacaoComplementar")
        or payload.get("descricaoDetalhada")
        or detail.get("descricaoDetalhada")
    )


def _has_catalog_metadata(item: ProcurementItem) -> bool:
    payload = item.source_payload or {}
    detail = payload.get("pncpItemDetail") if isinstance(payload.get("pncpItemDetail"), dict) else {}
    return bool(
        payload.get("catalogoCodigoItem")
        or detail.get("catalogoCodigoItem")
        or payload.get("codigoItemCatalogo")
        or detail.get("codigoItemCatalogo")
    )


def _normalized_unit(unit: str) -> str:
    return str(unit or "").upper().replace("/", " ").replace("-", " ").strip()
