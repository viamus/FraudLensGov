from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class ProcurementItem:
    id: str
    source: str
    source_record_id: str
    procurement_id: str
    item_code: str
    item_description: str
    unit: str
    quantity: float
    unit_price: float
    total_value: float
    currency: str
    agency_name: str
    agency_id: str
    supplier_name: str
    supplier_id: str
    city: str
    state: str
    procurement_date: str
    modality: str
    portal_url: str = ""
    source_payload: dict[str, Any] = field(default_factory=dict)
    inserted_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class Alert:
    id: str
    item_id: str
    risk_type: str
    severity: int
    score: float
    title: str
    explanation: str
    evidence: dict[str, Any]
    genai_explanation: str = ""
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class IngestionRun:
    id: str
    source: str
    status: str
    parameters: dict[str, Any]
    records_read: int = 0
    records_written: int = 0
    error: str = ""
    started_at: str = field(default_factory=utc_now)
    finished_at: str = ""


@dataclass(frozen=True)
class ItemCluster:
    id: str
    label: str
    item_count: int
    avg_unit_price: float
    min_unit_price: float
    max_unit_price: float
    total_value: float
    states: list[str]
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class ItemClusterMember:
    cluster_id: str
    item_id: str
    similarity: float


@dataclass(frozen=True)
class ItemNeighbor:
    item_id: str
    neighbor_item_id: str
    similarity: float
    rank: int


@dataclass(frozen=True)
class ItemCategorySuggestion:
    item_id: str
    canonical_name: str
    category: str
    confidence: float
    method: str
    evidence: dict[str, Any]
    created_at: str = field(default_factory=utc_now)
