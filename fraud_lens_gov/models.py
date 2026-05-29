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
