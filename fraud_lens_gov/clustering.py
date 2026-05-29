from __future__ import annotations

import re
from collections import Counter, defaultdict

from .models import ItemCluster, ItemClusterMember, ProcurementItem
from .normalization import stable_id


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
    "SERVICO",
    "SERVICOS",
}


def build_item_clusters(
    items: list[ProcurementItem],
    k: int = 8,
    min_similarity: float = 0.42,
) -> tuple[list[ItemCluster], list[ItemClusterMember]]:
    comparable = [item for item in items if _tokens(item.item_description)]
    neighbor_map = nearest_neighbors(comparable, k=k, min_similarity=min_similarity)
    graph: dict[str, set[str]] = {item.id: set() for item in comparable}
    by_id = {item.id: item for item in comparable}

    for item_id, neighbors in neighbor_map.items():
        for neighbor_id, _ in neighbors:
            graph[item_id].add(neighbor_id)
            graph[neighbor_id].add(item_id)

    clusters: list[ItemCluster] = []
    members: list[ItemClusterMember] = []
    visited: set[str] = set()

    for item in comparable:
        if item.id in visited:
            continue
        component_ids = _component(item.id, graph, visited)
        component_items = [by_id[item_id] for item_id in component_ids]
        label = _cluster_label(component_items)
        cluster_id = stable_id("cluster", label, ",".join(sorted(component_ids)))
        prices = [row.unit_price for row in component_items if row.unit_price > 0]
        clusters.append(
            ItemCluster(
                id=cluster_id,
                label=label,
                item_count=len(component_items),
                avg_unit_price=sum(prices) / len(prices) if prices else 0.0,
                min_unit_price=min(prices) if prices else 0.0,
                max_unit_price=max(prices) if prices else 0.0,
                total_value=sum(row.total_value for row in component_items),
                states=sorted({row.state for row in component_items if row.state}),
            )
        )
        for row in component_items:
            members.append(
                ItemClusterMember(
                    cluster_id=cluster_id,
                    item_id=row.id,
                    similarity=_member_similarity(row, component_items),
                )
            )

    return (
        sorted(clusters, key=lambda row: (row.item_count, row.total_value), reverse=True),
        members,
    )


def nearest_neighbors(
    items: list[ProcurementItem],
    k: int = 8,
    min_similarity: float = 0.42,
) -> dict[str, list[tuple[str, float]]]:
    result: dict[str, list[tuple[str, float]]] = {}
    for item in items:
        scored: list[tuple[str, float]] = []
        for candidate in items:
            if candidate.id == item.id:
                continue
            score = item_similarity(item, candidate)
            if score >= min_similarity:
                scored.append((candidate.id, score))
        result[item.id] = sorted(scored, key=lambda pair: pair[1], reverse=True)[:k]
    return result


def item_similarity(left: ProcurementItem, right: ProcurementItem) -> float:
    left_tokens = _tokens(left.item_description)
    right_tokens = _tokens(right.item_description)
    if not left_tokens or not right_tokens:
        return 0.0
    score = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    if left.state and left.state == right.state:
        score += 0.12
    if left.unit and left.unit == right.unit:
        score += 0.05
    if left.item_code and left.item_code == right.item_code:
        score += 0.12
    return min(score, 1.0)


def _component(start: str, graph: dict[str, set[str]], visited: set[str]) -> list[str]:
    stack = [start]
    component: list[str] = []
    while stack:
        item_id = stack.pop()
        if item_id in visited:
            continue
        visited.add(item_id)
        component.append(item_id)
        stack.extend(sorted(graph[item_id] - visited))
    return component


def _member_similarity(item: ProcurementItem, cluster_items: list[ProcurementItem]) -> float:
    others = [row for row in cluster_items if row.id != item.id]
    if not others:
        return 1.0
    score = sum(item_similarity(item, other) for other in others) / len(others)
    return round(score, 4)


def _cluster_label(items: list[ProcurementItem]) -> str:
    counts: Counter[str] = Counter()
    sources: defaultdict[str, int] = defaultdict(int)
    for item in items:
        tokens = _tokens(item.item_description)
        counts.update(tokens)
        for token in tokens:
            sources[token] += 1
    ranked = sorted(counts, key=lambda token: (sources[token], counts[token], token), reverse=True)
    label = " ".join(ranked[:6])
    return label or items[0].item_description[:80]


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[A-Z0-9]{2,}", text.upper()) if token not in STOPWORDS}
