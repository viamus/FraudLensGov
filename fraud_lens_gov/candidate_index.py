from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable

from .models import ProcurementItem


TokenFunc = Callable[[str], set[str]]


@dataclass(frozen=True)
class CandidateIndex:
    by_id: dict[str, ProcurementItem]
    tokens_by_id: dict[str, set[str]]
    token_index: dict[str, set[str]]
    code_index: dict[str, set[str]]
    code_by_id: dict[str, str]


def build_candidate_index(items: list[ProcurementItem], token_func: TokenFunc) -> CandidateIndex:
    by_id = {item.id: item for item in items}
    tokens_by_id: dict[str, set[str]] = {}
    token_index: defaultdict[str, set[str]] = defaultdict(set)
    code_index: defaultdict[str, set[str]] = defaultdict(set)
    code_by_id: dict[str, str] = {}

    for item in items:
        tokens = token_func(item.item_description)
        tokens_by_id[item.id] = tokens
        for token in tokens:
            token_index[token].add(item.id)
        code = meaningful_item_code(item)
        code_by_id[item.id] = code
        if code:
            code_index[code].add(item.id)

    return CandidateIndex(
        by_id=by_id,
        tokens_by_id=tokens_by_id,
        token_index=dict(token_index),
        code_index=dict(code_index),
        code_by_id=code_by_id,
    )


def candidate_ids(
    item: ProcurementItem,
    index: CandidateIndex,
    *,
    max_candidates: int = 700,
    max_token_posting: int = 2500,
) -> list[str]:
    tokens = index.tokens_by_id.get(item.id, set())
    candidates: set[str] = set()
    item_code = index.code_by_id.get(item.id, "")

    if item_code:
        code_posting = index.code_index.get(item_code, set())
        if len(code_posting) <= max_token_posting:
            candidates.update(code_posting)

    ranked_tokens = sorted(tokens, key=lambda token: len(index.token_index.get(token, set())))
    for token in ranked_tokens:
        posting = index.token_index.get(token, set())
        if len(posting) > max_token_posting:
            continue
        candidates.update(posting)
        if len(candidates) >= max_candidates * 3:
            break

    candidates.discard(item.id)
    if len(candidates) <= max_candidates:
        return sorted(candidates)

    return sorted(
        candidates,
        key=lambda candidate_id: _quick_score(item, candidate_id, index, tokens, item_code),
        reverse=True,
    )[:max_candidates]


def meaningful_item_code(item: ProcurementItem) -> str:
    code = str(item.item_code or "").strip()
    if not code:
        return ""
    payload = item.source_payload or {}
    detail = payload.get("pncpItemDetail") if isinstance(payload.get("pncpItemDetail"), dict) else {}
    blocked_codes = {
        str(item.source_record_id or ""),
        str(payload.get("idCompraItem") or ""),
        str(payload.get("id_compra_item") or ""),
        str(payload.get("numeroItemPncp") or ""),
        str(payload.get("numero_item_pncp") or ""),
        str(payload.get("numeroItem") or ""),
        str(payload.get("numero_item") or ""),
        str(detail.get("numeroItem") or ""),
    }
    return "" if code in blocked_codes else code


def _quick_score(
    item: ProcurementItem,
    candidate_id: str,
    index: CandidateIndex,
    tokens: set[str],
    item_code: str,
) -> tuple[float, float]:
    candidate = index.by_id[candidate_id]
    candidate_tokens = index.tokens_by_id.get(candidate_id, set())
    token_score = 0.0
    if tokens and candidate_tokens:
        token_score = len(tokens & candidate_tokens) / len(tokens | candidate_tokens)
    boost = 0.0
    if item.state and item.state == candidate.state:
        boost += 0.08
    if item.unit and item.unit == candidate.unit:
        boost += 0.04
    if item_code and item_code == index.code_by_id.get(candidate_id, ""):
        boost += 0.12
    return (token_score + boost, candidate.total_value)
