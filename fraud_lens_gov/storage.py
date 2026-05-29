from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .models import Alert, ProcurementItem


class Storage:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS procurement_items (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    source_record_id TEXT NOT NULL,
                    procurement_id TEXT NOT NULL,
                    item_code TEXT NOT NULL,
                    item_description TEXT NOT NULL,
                    unit TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    unit_price REAL NOT NULL,
                    total_value REAL NOT NULL,
                    currency TEXT NOT NULL,
                    agency_name TEXT NOT NULL,
                    agency_id TEXT NOT NULL,
                    supplier_name TEXT NOT NULL,
                    supplier_id TEXT NOT NULL,
                    city TEXT NOT NULL,
                    state TEXT NOT NULL,
                    procurement_date TEXT NOT NULL,
                    modality TEXT NOT NULL,
                    portal_url TEXT NOT NULL,
                    source_payload TEXT NOT NULL,
                    inserted_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_items_description_state
                    ON procurement_items(item_description, state);

                CREATE INDEX IF NOT EXISTS idx_items_supplier
                    ON procurement_items(supplier_id, supplier_name);

                CREATE TABLE IF NOT EXISTS analysis_alerts (
                    id TEXT PRIMARY KEY,
                    item_id TEXT NOT NULL,
                    risk_type TEXT NOT NULL,
                    severity INTEGER NOT NULL,
                    score REAL NOT NULL,
                    title TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    genai_explanation TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(item_id) REFERENCES procurement_items(id) ON DELETE CASCADE
                );
                """
            )

    def upsert_items(self, items: Iterable[ProcurementItem]) -> int:
        rows = list(items)
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO procurement_items (
                    id, source, source_record_id, procurement_id, item_code, item_description,
                    unit, quantity, unit_price, total_value, currency, agency_name, agency_id,
                    supplier_name, supplier_id, city, state, procurement_date, modality,
                    portal_url, source_payload, inserted_at
                )
                VALUES (
                    :id, :source, :source_record_id, :procurement_id, :item_code, :item_description,
                    :unit, :quantity, :unit_price, :total_value, :currency, :agency_name, :agency_id,
                    :supplier_name, :supplier_id, :city, :state, :procurement_date, :modality,
                    :portal_url, :source_payload, :inserted_at
                )
                ON CONFLICT(id) DO UPDATE SET
                    source_payload = excluded.source_payload,
                    inserted_at = excluded.inserted_at
                """,
                [self._item_to_row(item) for item in rows],
            )
        return len(rows)

    def list_items(self, limit: int | None = None) -> list[ProcurementItem]:
        sql = "SELECT * FROM procurement_items ORDER BY procurement_date DESC, total_value DESC"
        params: tuple[int, ...] = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        with self.connect() as conn:
            return [self._row_to_item(row) for row in conn.execute(sql, params).fetchall()]

    def count_items(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM procurement_items").fetchone()[0])

    def replace_alerts(self, alerts: Iterable[Alert]) -> None:
        rows = list(alerts)
        with self.connect() as conn:
            conn.execute("DELETE FROM analysis_alerts")
            conn.executemany(
                """
                INSERT INTO analysis_alerts (
                    id, item_id, risk_type, severity, score, title, explanation,
                    evidence, genai_explanation, created_at
                )
                VALUES (
                    :id, :item_id, :risk_type, :severity, :score, :title, :explanation,
                    :evidence, :genai_explanation, :created_at
                )
                """,
                [self._alert_to_row(alert) for alert in rows],
            )

    def list_alerts(self, limit: int | None = None) -> list[Alert]:
        sql = "SELECT * FROM analysis_alerts ORDER BY severity DESC, score DESC, created_at DESC"
        params: tuple[int, ...] = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        with self.connect() as conn:
            return [self._row_to_alert(row) for row in conn.execute(sql, params).fetchall()]

    def update_alert_explanations(self, alerts: Iterable[Alert]) -> None:
        with self.connect() as conn:
            conn.executemany(
                "UPDATE analysis_alerts SET genai_explanation = ? WHERE id = ?",
                [(alert.genai_explanation, alert.id) for alert in alerts],
            )

    def dashboard_summary(self) -> dict[str, object]:
        with self.connect() as conn:
            totals = conn.execute(
                """
                SELECT
                    COUNT(*) AS items,
                    COALESCE(SUM(total_value), 0) AS total_value,
                    COUNT(DISTINCT supplier_id || supplier_name) AS suppliers,
                    COUNT(DISTINCT agency_id || agency_name) AS agencies
                FROM procurement_items
                """
            ).fetchone()
            alerts = conn.execute(
                """
                SELECT
                    COUNT(*) AS alerts,
                    COALESCE(MAX(severity), 0) AS max_severity,
                    COALESCE(AVG(score), 0) AS avg_score
                FROM analysis_alerts
                """
            ).fetchone()
            risk_types = conn.execute(
                """
                SELECT risk_type, COUNT(*) AS count
                FROM analysis_alerts
                GROUP BY risk_type
                ORDER BY count DESC
                """
            ).fetchall()
            top_alerts = conn.execute(
                """
                SELECT a.*, i.item_description, i.agency_name, i.supplier_name, i.state,
                       i.unit_price, i.total_value, i.procurement_date
                FROM analysis_alerts a
                JOIN procurement_items i ON i.id = a.item_id
                ORDER BY a.severity DESC, a.score DESC
                LIMIT 25
                """
            ).fetchall()
        return {
            "totals": dict(totals),
            "alerts": dict(alerts),
            "risk_types": [dict(row) for row in risk_types],
            "top_alerts": [dict(row) for row in top_alerts],
        }

    @staticmethod
    def _item_to_row(item: ProcurementItem) -> dict[str, object]:
        row = asdict(item)
        row["source_payload"] = json.dumps(item.source_payload, ensure_ascii=False, sort_keys=True)
        return row

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> ProcurementItem:
        data = dict(row)
        data["source_payload"] = json.loads(data["source_payload"] or "{}")
        return ProcurementItem(**data)

    @staticmethod
    def _alert_to_row(alert: Alert) -> dict[str, object]:
        row = asdict(alert)
        row["evidence"] = json.dumps(alert.evidence, ensure_ascii=False, sort_keys=True)
        return row

    @staticmethod
    def _row_to_alert(row: sqlite3.Row) -> Alert:
        data = dict(row)
        data["evidence"] = json.loads(data["evidence"] or "{}")
        return Alert(**data)
