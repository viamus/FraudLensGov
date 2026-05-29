from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median
import re

from .models import Alert, ProcurementItem
from .item_quality import is_comparable
from .normalization import stable_id


STOPWORDS = {
    "A",
    "AS",
    "COM",
    "DA",
    "DE",
    "DO",
    "DOS",
    "E",
    "EM",
    "ITEM",
    "PARA",
    "POR",
}


def analyze_items(items: list[ProcurementItem]) -> list[Alert]:
    alerts: list[Alert] = []
    alerts.extend(_price_outliers(items))
    alerts.extend(_supplier_concentration(items))
    alerts.extend(_fragmented_purchases(items))
    deduped = {alert.id: alert for alert in alerts}
    return sorted(deduped.values(), key=lambda alert: (alert.severity, alert.score), reverse=True)


def _price_outliers(items: list[ProcurementItem]) -> list[Alert]:
    alerts: list[Alert] = []
    priced_items = [item for item in items if item.unit_price > 0 and is_comparable(item)]
    for item in priced_items:
        neighbors = _nearest_price_neighbors(item, priced_items)
        if len(neighbors) < 3:
            continue
        prices = [neighbor.unit_price for neighbor, _ in neighbors]
        baseline = median(prices)
        if baseline <= 0:
            continue
        ratio = item.unit_price / baseline
        if ratio >= 1.8:
            severity = 3 if ratio >= 2.5 else 2
            alerts.append(
                Alert(
                    id=stable_id("price_outlier", item.id, round(ratio, 2)),
                    item_id=item.id,
                    risk_type="price_outlier",
                    severity=severity,
                    score=round(min(ratio / 3.0, 1.0), 4),
                    title="Preco unitario acima de vizinhos comparaveis",
                    explanation=(
                        f"O preco unitario de R$ {item.unit_price:,.2f} esta "
                        f"{ratio:.1f}x acima da mediana dos vizinhos de R$ {baseline:,.2f}."
                    ),
                    evidence={
                        "method": "textual_knn_median",
                        "unit_price": item.unit_price,
                        "neighbor_median": baseline,
                        "ratio": ratio,
                        "comparison_count": len(neighbors),
                        "item_description": item.item_description,
                        "state": item.state,
                        "neighbors": [
                            {
                                "item_id": neighbor.id,
                                "description": neighbor.item_description,
                                "state": neighbor.state,
                                "unit_price": neighbor.unit_price,
                                "similarity": round(similarity, 4),
                            }
                            for neighbor, similarity in neighbors[:5]
                        ],
                    },
                )
            )
    return alerts


def _nearest_price_neighbors(
    item: ProcurementItem,
    candidates: list[ProcurementItem],
    k: int = 12,
    min_similarity: float = 0.45,
) -> list[tuple[ProcurementItem, float]]:
    scored: list[tuple[ProcurementItem, float]] = []
    for candidate in candidates:
        if candidate.id == item.id:
            continue
        if not is_comparable(candidate):
            continue
        similarity = _item_similarity(item, candidate)
        if similarity >= min_similarity:
            scored.append((candidate, similarity))
    return sorted(scored, key=lambda pair: (pair[1], -pair[0].unit_price), reverse=True)[:k]


def _item_similarity(left: ProcurementItem, right: ProcurementItem) -> float:
    left_tokens = _tokens(left.item_description)
    right_tokens = _tokens(right.item_description)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    score = overlap / union
    if left.state and left.state == right.state:
        score += 0.15
    if left.unit and left.unit == right.unit:
        score += 0.05
    if left.item_code and left.item_code == right.item_code:
        score += 0.10
    return min(score, 1.0)


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[A-Z0-9]{2,}", text.upper()) if token not in STOPWORDS}


def _supplier_concentration(items: list[ProcurementItem]) -> list[Alert]:
    grouped: dict[tuple[str, str], list[ProcurementItem]] = defaultdict(list)
    for item in items:
        if not is_comparable(item):
            continue
        if item.supplier_id or item.supplier_name:
            grouped[(item.agency_id or item.agency_name, item.item_description)].append(item)

    alerts: list[Alert] = []
    for (_, _), group in grouped.items():
        if len(group) < 4:
            continue
        supplier_counts = Counter(item.supplier_id or item.supplier_name for item in group)
        supplier, wins = supplier_counts.most_common(1)[0]
        share = wins / len(group)
        if share >= 0.75:
            for item in group:
                if (item.supplier_id or item.supplier_name) == supplier:
                    alerts.append(
                        Alert(
                            id=stable_id("supplier_concentration", item.id, wins, len(group)),
                            item_id=item.id,
                            risk_type="supplier_concentration",
                            severity=2,
                            score=round(share, 4),
                            title="Fornecedor recorrente no mesmo orgao e item",
                            explanation=(
                                f"O fornecedor venceu {wins} de {len(group)} registros comparaveis "
                                f"para o mesmo orgao e item."
                            ),
                            evidence={
                                "supplier": supplier,
                                "wins": wins,
                                "comparison_count": len(group),
                                "share": share,
                                "agency": item.agency_name,
                                "item_description": item.item_description,
                            },
                        )
                    )
                    break
    return alerts


def _fragmented_purchases(items: list[ProcurementItem]) -> list[Alert]:
    grouped: dict[tuple[str, str, str], list[ProcurementItem]] = defaultdict(list)
    for item in items:
        if not is_comparable(item):
            continue
        month = item.procurement_date[:7]
        if month:
            grouped[(item.agency_id or item.agency_name, item.item_description, month)].append(item)

    alerts: list[Alert] = []
    for (_, _, _), group in grouped.items():
        if len(group) < 3:
            continue
        total = sum(item.total_value for item in group)
        values = [item.total_value for item in group if item.total_value > 0]
        if not values:
            continue
        close_values = sum(1 for value in values if value <= 60000)
        if close_values >= 3 and total >= 100000:
            item = max(group, key=lambda current: current.total_value)
            alerts.append(
                Alert(
                    id=stable_id("fragmented_purchase", item.agency_id, item.item_description, item.procurement_date[:7]),
                    item_id=item.id,
                    risk_type="fragmented_purchase",
                    severity=2,
                    score=round(min(total / 250000, 1.0), 4),
                    title="Possivel fracionamento de compras",
                    explanation=(
                        f"Foram encontrados {len(group)} registros do mesmo item no mesmo orgao e mes, "
                        f"somando R$ {total:,.2f}."
                    ),
                    evidence={
                        "records": len(group),
                        "monthly_total": total,
                        "agency": item.agency_name,
                        "item_description": item.item_description,
                        "month": item.procurement_date[:7],
                    },
                )
            )
    return alerts
