from __future__ import annotations

import re
from collections import Counter

from .candidate_index import meaningful_item_code
from .item_quality import description_quality
from .models import ItemCategorySuggestion, ProcurementItem


CATEGORY_RULES: tuple[tuple[str, set[str]], ...] = (
    ("Saude e atendimento medico", {"MEDICA", "MEDICO", "MEDICINA", "PSICOLOGIA", "PSIQUIATRIA", "ENFERMAGEM", "HOSPITAL", "CLINICA", "ODONTOLOGICO", "FARMACEUTICO"}),
    ("Medicamentos e insumos de saude", {"MEDICAMENTO", "FARMACO", "VACINA", "SERINGA", "AGULHA", "CURATIVO", "REAGENTE"}),
    ("Tecnologia da informacao", {"COMPUTADOR", "NOTEBOOK", "IMPRESSORA", "SOFTWARE", "LICENCA", "SERVIDOR", "REDE", "INFORMATICA", "TABLET"}),
    ("Laboratorio e pesquisa", {"LABORATORIO", "MICROSCOPIO", "PIPETA", "CENTRIFUGA", "ANALISADOR", "ENSAIO"}),
    ("Obras e manutencao predial", {"OBRA", "ENGENHARIA", "REFORMA", "CONSTRUCAO", "MANUTENCAO", "PREDIAL", "ASFALTO", "PAVIMENTACAO"}),
    ("Limpeza e conservacao", {"LIMPEZA", "HIGIENIZACAO", "CONSERVACAO", "DESINFECCAO", "SANEANTE"}),
    ("Alimentacao", {"ALIMENTO", "ALIMENTACAO", "MERENDA", "REFEICAO", "CESTA", "LEITE", "CARNE", "ARROZ"}),
    ("Transporte e veiculos", {"VEICULO", "AUTOMOVEL", "CAMINHAO", "ONIBUS", "TRANSPORTE", "COMBUSTIVEL", "PNEU"}),
    ("Seguranca", {"SEGURANCA", "VIGILANCIA", "MONITORAMENTO", "CAMERA", "ALARME"}),
    ("Mobiliario e equipamentos", {"MESA", "CADEIRA", "ARMARIO", "MOBILIARIO", "EQUIPAMENTO", "APARELHO"}),
    ("Servicos profissionais", {"CONSULTORIA", "ASSESSORIA", "TREINAMENTO", "CAPACITACAO", "TERAPIA", "SERVICO", "SERVICOS"}),
    ("Material administrativo", {"EXPEDIENTE", "PAPEL", "CANETA", "TONER", "PASTA", "ENVELOPE"}),
)

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
    "MATERIAL",
    "PARA",
    "POR",
    "SERVICO",
    "SERVICOS",
    "UNIDADE",
}


def categorize_items(items: list[ProcurementItem]) -> list[ItemCategorySuggestion]:
    return [categorize_item(item) for item in items]


def categorize_item(item: ProcurementItem) -> ItemCategorySuggestion:
    quality = description_quality(item)
    tokens = _tokens(item.item_description)
    code = meaningful_item_code(item)
    category, matched_tokens = _category_for(tokens)
    canonical_tokens = _canonical_tokens(tokens, matched_tokens)
    canonical_name = " ".join(canonical_tokens) or category

    confidence = _confidence(quality, tokens, matched_tokens, code)
    method = "lexical_rules_v1"
    if quality.get("level") == "procurement_scope":
        method = "procurement_scope"
        category = "Escopo de contratacao"
        canonical_name = "Objeto de contratacao"
        confidence = 0.2
    elif quality.get("level") == "missing":
        method = "missing_description"
        category = "Descricao ausente"
        canonical_name = "Descricao de item nao publicada"
        confidence = 0.0

    return ItemCategorySuggestion(
        item_id=item.id,
        canonical_name=canonical_name,
        category=category,
        confidence=round(confidence, 4),
        method=method,
        evidence={
            "item_code": code,
            "tokens": sorted(tokens),
            "matched_tokens": sorted(matched_tokens),
            "quality_level": quality.get("level"),
            "quality_reason": quality.get("reason"),
            "rag_ready": {
                "needs_rag": quality.get("level") in {"generic", "weak", "missing"} or confidence < 0.55,
                "target_evidence": ["descricao detalhada", "catalogo", "termo de referencia", "edital"],
            },
        },
    )


def _category_for(tokens: set[str]) -> tuple[str, set[str]]:
    best_category = "Nao classificado"
    best_matches: set[str] = set()
    for category, rule_tokens in CATEGORY_RULES:
        matches = tokens & rule_tokens
        if len(matches) > len(best_matches):
            best_category = category
            best_matches = matches
    return best_category, best_matches


def _canonical_tokens(tokens: set[str], matched_tokens: set[str]) -> list[str]:
    useful = [token for token in tokens if token not in STOPWORDS]
    counts = Counter(useful)
    ranked = sorted(counts, key=lambda token: (token in matched_tokens, counts[token], len(token), token), reverse=True)
    return ranked[:5]


def _confidence(quality: dict[str, object], tokens: set[str], matched_tokens: set[str], code: str) -> float:
    score = 0.18
    if quality.get("comparable"):
        score += 0.24
    if matched_tokens:
        score += min(0.28, 0.12 + len(matched_tokens) * 0.08)
    if code:
        score += 0.12
    if len(tokens) >= 5:
        score += 0.12
    elif len(tokens) >= 3:
        score += 0.06
    if quality.get("level") in {"generic", "weak"}:
        score -= 0.16
    return max(0.0, min(score, 0.95))


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[A-Z0-9]{2,}", text.upper()) if token not in STOPWORDS}
