from __future__ import annotations

import re
from dataclasses import dataclass

from .candidate_index import meaningful_item_code
from .models import ProcurementItem
from .unit_normalization import comparable_units


STOPWORDS = {
    "A",
    "AS",
    "COM",
    "CONTRATACAO",
    "DA",
    "DE",
    "DO",
    "DOS",
    "E",
    "EM",
    "ITEM",
    "PARA",
    "POR",
    "REGISTRO",
}

CONTEXT_TERMS = {
    "ADMINISTRATIVO",
    "AMBULATORIAL",
    "CLINICO",
    "CLINICA",
    "DENTAL",
    "ESCOLAR",
    "HOSPITAL",
    "HOSPITALAR",
    "LABORATORIO",
    "LABORATORIAL",
    "MEDICA",
    "MEDICO",
    "ODONTOLOGICO",
    "PROFISSIONAL",
    "PUBLICO",
    "SAUDE",
    "USO",
}

GENERIC_TERMS = {
    "ACESSORIO",
    "ACESSORIOS",
    "APARELHO",
    "AQUISICAO",
    "CONJUNTO",
    "EQUIPAMENTO",
    "FORNECIMENTO",
    "INSUMO",
    "INSUMOS",
    "KIT",
    "MATERIAL",
    "MATERIAIS",
    "PECA",
    "PECAS",
    "PRODUTO",
    "PRODUTOS",
    "SERVICO",
    "SERVICOS",
    "UNIDADE",
}

ATTRIBUTE_TERMS = {
    "CAPACIDADE",
    "COR",
    "DIMENSAO",
    "DIMENSOES",
    "MARCA",
    "MODELO",
    "POLEGADA",
    "POLEGADAS",
    "TAMANHO",
    "TIPO",
}

SYNONYMS = {
    "UND": "UNIDADE",
    "UN": "UNIDADE",
    "PC": "PECA",
    "PCS": "PECA",
    "PÇ": "PECA",
    "PÇS": "PECA",
    "MICROCOMPUTADOR": "COMPUTADOR",
    "LAPTOP": "NOTEBOOK",
    "PORTATIL": "NOTEBOOK",
    "ODONTOLOGICA": "ODONTOLOGICO",
    "ODONTOLOGICOS": "ODONTOLOGICO",
    "MEDICAS": "MEDICA",
    "MEDICOS": "MEDICO",
    "HOSPITALARES": "HOSPITALAR",
    "LABORATORIAIS": "LABORATORIAL",
}

MEASURE_RE = re.compile(r"^\d+(?:[,.]\d+)?(?:KG|G|MG|L|ML|CM|MM|M|GB|MB|TB|W|V|UN)?$")
TOKEN_RE = re.compile(r"[A-Z0-9Ç]+")


@dataclass(frozen=True)
class SemanticProfile:
    tokens: set[str]
    identity_tokens: set[str]
    core_tokens: set[str]
    primary_token: str
    context_tokens: set[str]
    spec_tokens: set[str]
    item_code: str


def semantic_tokens(text: str) -> set[str]:
    profile = profile_from_text(text)
    return profile.identity_tokens or profile.tokens


def item_similarity(left: ProcurementItem, right: ProcurementItem) -> float:
    if not comparable_units(left, right):
        return 0.0

    left_profile = profile_for_item(left)
    right_profile = profile_for_item(right)
    same_code = bool(left_profile.item_code and left_profile.item_code == right_profile.item_code)
    if not same_code and not semantically_compatible(left_profile, right_profile):
        return 0.0

    identity_score = _jaccard(left_profile.identity_tokens, right_profile.identity_tokens)
    token_score = _jaccard(left_profile.tokens, right_profile.tokens)
    spec_score = _jaccard(left_profile.spec_tokens, right_profile.spec_tokens)
    context_score = _jaccard(left_profile.context_tokens, right_profile.context_tokens)

    score = (identity_score * 0.58) + (token_score * 0.22) + (spec_score * 0.10) + (context_score * 0.05)
    if same_code:
        score += 0.22
    if left.state and left.state == right.state:
        score += 0.05
    if left.unit and left.unit == right.unit:
        score += 0.05
    return min(score, 1.0)


def semantically_compatible(left: SemanticProfile, right: SemanticProfile) -> bool:
    if not left.identity_tokens or not right.identity_tokens:
        return False
    if left.primary_token and left.primary_token == right.primary_token:
        return True
    core_overlap = left.core_tokens & right.core_tokens
    if len(core_overlap) >= 2:
        return True
    identity_overlap = left.identity_tokens & right.identity_tokens
    if len(identity_overlap) < 2:
        return False
    if left.primary_token and left.primary_token not in identity_overlap:
        return False
    if right.primary_token and right.primary_token not in identity_overlap:
        return False
    left_coverage = len(identity_overlap) / len(left.identity_tokens)
    right_coverage = len(identity_overlap) / len(right.identity_tokens)
    return min(left_coverage, right_coverage) >= 0.5


def profile_for_item(item: ProcurementItem) -> SemanticProfile:
    profile = profile_from_text(item.item_description)
    return SemanticProfile(
        tokens=profile.tokens,
        identity_tokens=profile.identity_tokens,
        core_tokens=profile.core_tokens,
        primary_token=profile.primary_token,
        context_tokens=profile.context_tokens,
        spec_tokens=profile.spec_tokens,
        item_code=meaningful_item_code(item),
    )


def profile_from_text(text: str) -> SemanticProfile:
    raw_tokens = [_normalize_token(token) for token in TOKEN_RE.findall(str(text or "").upper())]
    ordered = [token for token in raw_tokens if token and token not in STOPWORDS]
    tokens = set(ordered)
    context_tokens = {token for token in tokens if token in CONTEXT_TERMS}
    spec_tokens = {token for token in tokens if token in ATTRIBUTE_TERMS or MEASURE_RE.match(token)}
    identity_ordered = [
        token
        for token in ordered
        if token not in CONTEXT_TERMS and token not in GENERIC_TERMS and token not in ATTRIBUTE_TERMS
    ]
    identity_tokens = set(identity_ordered)
    core_tokens = set(identity_ordered[:2])
    primary_token = identity_ordered[0] if identity_ordered else ""
    return SemanticProfile(
        tokens=tokens,
        identity_tokens=identity_tokens,
        core_tokens=core_tokens,
        primary_token=primary_token,
        context_tokens=context_tokens,
        spec_tokens=spec_tokens,
        item_code="",
    )


def _normalize_token(token: str) -> str:
    token = SYNONYMS.get(token, token)
    if token in SYNONYMS:
        return SYNONYMS[token]
    if len(token) > 5 and token.endswith("OES"):
        token = f"{token[:-3]}AO"
    elif len(token) > 5 and token.endswith("ORES"):
        token = token[:-2]
    elif len(token) > 4 and token.endswith("AIS"):
        token = f"{token[:-3]}AL"
    elif len(token) > 4 and token.endswith("S") and not token.endswith("GBS"):
        token = token[:-1]
    return SYNONYMS.get(token, token)


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
