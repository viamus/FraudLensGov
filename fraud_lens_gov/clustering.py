from __future__ import annotations

from collections import Counter, defaultdict

from .models import ItemCluster, ItemClusterMember, ItemNeighbor, ProcurementItem
from .candidate_index import build_candidate_index, candidate_ids
from .item_quality import is_comparable
from .normalization import stable_id
from .semantic_similarity import item_similarity, semantic_tokens
from .unit_normalization import adjusted_unit_price, comparable_units, is_price_benchmarkable


def build_item_clusters(
    items: list[ProcurementItem],
    k: int = 8,
    min_similarity: float = 0.42,
) -> tuple[list[ItemCluster], list[ItemClusterMember]]:
    clusters, members, _ = build_cluster_index(items, k=k, min_similarity=min_similarity)
    return clusters, members


def build_cluster_index(
    items: list[ProcurementItem],
    k: int = 8,
    min_similarity: float = 0.42,
) -> tuple[list[ItemCluster], list[ItemClusterMember], list[ItemNeighbor]]:
    comparable = [
        item for item in items if is_comparable(item) and is_price_benchmarkable(item) and semantic_tokens(item.item_description)
    ]
    neighbor_map = nearest_neighbors(comparable, k=k, min_similarity=min_similarity)
    graph: dict[str, set[str]] = {item.id: set() for item in comparable}
    by_id = {item.id: item for item in comparable}
    neighbor_rows: list[ItemNeighbor] = []

    for item_id, neighbors in neighbor_map.items():
        for rank, (neighbor_id, similarity) in enumerate(neighbors, start=1):
            graph[item_id].add(neighbor_id)
            graph[neighbor_id].add(item_id)
            neighbor_rows.append(
                ItemNeighbor(
                    item_id=item_id,
                    neighbor_item_id=neighbor_id,
                    similarity=round(similarity, 4),
                    rank=rank,
                )
            )

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
        prices = [adjusted_unit_price(row) for row in component_items if adjusted_unit_price(row) > 0]
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
        neighbor_rows,
    )


def nearest_neighbors(
    items: list[ProcurementItem],
    k: int = 8,
    min_similarity: float = 0.42,
) -> dict[str, list[tuple[str, float]]]:
    index = build_candidate_index(items, semantic_tokens)
    result: dict[str, list[tuple[str, float]]] = {}
    for item in items:
        scored: list[tuple[str, float]] = []
        for candidate_id in candidate_ids(item, index, max_candidates=max(700, k * 80)):
            candidate = index.by_id[candidate_id]
            if not comparable_units(item, candidate):
                continue
            score = item_similarity(item, candidate)
            if score >= min_similarity:
                scored.append((candidate.id, score))
        result[item.id] = sorted(scored, key=lambda pair: pair[1], reverse=True)[:k]
    return result


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
        tokens = semantic_tokens(item.item_description)
        counts.update(tokens)
        for token in tokens:
            sources[token] += 1
    ranked = sorted(counts, key=lambda token: (sources[token], counts[token], token), reverse=True)
    label = " ".join(ranked[:6])
    return label or items[0].item_description[:80]
