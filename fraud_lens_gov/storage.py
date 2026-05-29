from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .models import Alert, IngestionRun, ItemCluster, ItemClusterMember, ItemNeighbor, ProcurementItem, utc_now
from .item_quality import description_quality
from .normalization import stable_id


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

                CREATE TABLE IF NOT EXISTS bronze_records (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    source_record_id TEXT NOT NULL,
                    procurement_id TEXT NOT NULL,
                    item_number TEXT NOT NULL,
                    record_date TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    parameters TEXT NOT NULL,
                    silver_status TEXT NOT NULL,
                    silver_error TEXT NOT NULL,
                    collected_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_items_description_state
                    ON procurement_items(item_description, state);

                CREATE INDEX IF NOT EXISTS idx_items_supplier
                    ON procurement_items(supplier_id, supplier_name);

                CREATE INDEX IF NOT EXISTS idx_bronze_records_source_status
                    ON bronze_records(source, silver_status, record_date);

                CREATE INDEX IF NOT EXISTS idx_bronze_records_procurement
                    ON bronze_records(procurement_id, item_number);

                CREATE TABLE IF NOT EXISTS golden_items (
                    item_id TEXT PRIMARY KEY,
                    quality_level TEXT NOT NULL,
                    comparable INTEGER NOT NULL,
                    quality_reason TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    built_at TEXT NOT NULL,
                    FOREIGN KEY(item_id) REFERENCES procurement_items(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS pipeline_jobs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    layer TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_step TEXT NOT NULL,
                    steps_total INTEGER NOT NULL,
                    steps_done INTEGER NOT NULL,
                    progress REAL NOT NULL,
                    message TEXT NOT NULL,
                    error TEXT NOT NULL,
                    parameters TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_status
                    ON pipeline_jobs(status, started_at);

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

                CREATE TABLE IF NOT EXISTS ingestion_runs (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    parameters TEXT NOT NULL,
                    records_read INTEGER NOT NULL,
                    records_written INTEGER NOT NULL,
                    error TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS item_clusters (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    item_count INTEGER NOT NULL,
                    avg_unit_price REAL NOT NULL,
                    min_unit_price REAL NOT NULL,
                    max_unit_price REAL NOT NULL,
                    total_value REAL NOT NULL,
                    states TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS item_cluster_members (
                    cluster_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    similarity REAL NOT NULL,
                    PRIMARY KEY(cluster_id, item_id),
                    FOREIGN KEY(cluster_id) REFERENCES item_clusters(id) ON DELETE CASCADE,
                    FOREIGN KEY(item_id) REFERENCES procurement_items(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS item_neighbors (
                    item_id TEXT NOT NULL,
                    neighbor_item_id TEXT NOT NULL,
                    similarity REAL NOT NULL,
                    rank INTEGER NOT NULL,
                    PRIMARY KEY(item_id, neighbor_item_id),
                    FOREIGN KEY(item_id) REFERENCES procurement_items(id) ON DELETE CASCADE,
                    FOREIGN KEY(neighbor_item_id) REFERENCES procurement_items(id) ON DELETE CASCADE
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
                    source = excluded.source,
                    source_record_id = excluded.source_record_id,
                    procurement_id = excluded.procurement_id,
                    item_code = excluded.item_code,
                    item_description = excluded.item_description,
                    unit = excluded.unit,
                    quantity = excluded.quantity,
                    unit_price = excluded.unit_price,
                    total_value = excluded.total_value,
                    currency = excluded.currency,
                    agency_name = excluded.agency_name,
                    agency_id = excluded.agency_id,
                    supplier_name = excluded.supplier_name,
                    supplier_id = excluded.supplier_id,
                    city = excluded.city,
                    state = excluded.state,
                    procurement_date = excluded.procurement_date,
                    modality = excluded.modality,
                    portal_url = excluded.portal_url,
                    source_payload = excluded.source_payload,
                    inserted_at = excluded.inserted_at
                """,
                [self._item_to_row(item) for item in rows],
            )
        return len(rows)

    def upsert_bronze_records(
        self,
        source: str,
        records: Iterable[dict[str, object]],
        parameters: dict[str, object],
    ) -> int:
        rows = [self._bronze_record_to_row(source, record, parameters) for record in records]
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO bronze_records (
                    id, source, source_record_id, procurement_id, item_number,
                    record_date, payload, parameters, silver_status, silver_error, collected_at
                )
                VALUES (
                    :id, :source, :source_record_id, :procurement_id, :item_number,
                    :record_date, :payload, :parameters, :silver_status, :silver_error, :collected_at
                )
                ON CONFLICT(id) DO UPDATE SET
                    payload = excluded.payload,
                    parameters = excluded.parameters,
                    silver_status = 'pending',
                    silver_error = '',
                    collected_at = excluded.collected_at
                """,
                rows,
            )
        return len(rows)

    def bronze_records_for_silver(
        self,
        source: str = "both",
        limit: int | None = None,
        status: str = "pending",
    ) -> list[dict[str, object]]:
        params: list[object] = [status]
        source_filter = ""
        if source != "both":
            source_filter = "AND source = ?"
            params.append(source)
        limit_clause = ""
        if limit is not None:
            limit_clause = "LIMIT ?"
            params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM bronze_records
                WHERE silver_status = ?
                {source_filter}
                ORDER BY record_date ASC, collected_at ASC
                {limit_clause}
                """,
                tuple(params),
            ).fetchall()
        return [self._bronze_row_to_dict(row) for row in rows]

    def mark_bronze_silver_status(self, ids: Iterable[str], status: str, error: str = "") -> None:
        rows = [(status, error, row_id) for row_id in ids]
        if not rows:
            return
        with self.connect() as conn:
            conn.executemany(
                """
                UPDATE bronze_records
                SET silver_status = ?, silver_error = ?
                WHERE id = ?
                """,
                rows,
            )

    def replace_golden_items(self, items: Iterable[ProcurementItem]) -> int:
        rows = []
        built_at = utc_now()
        for item in items:
            quality = description_quality(item)
            rows.append(
                {
                    "item_id": item.id,
                    "quality_level": str(quality.get("level") or "unknown"),
                    "comparable": 1 if quality.get("comparable") else 0,
                    "quality_reason": str(quality.get("reason") or ""),
                    "metadata": json.dumps(quality, ensure_ascii=False, sort_keys=True),
                    "built_at": built_at,
                }
            )
        with self.connect() as conn:
            conn.execute("DELETE FROM golden_items")
            conn.executemany(
                """
                INSERT INTO golden_items (
                    item_id, quality_level, comparable, quality_reason, metadata, built_at
                )
                VALUES (
                    :item_id, :quality_level, :comparable, :quality_reason, :metadata, :built_at
                )
                """,
                rows,
            )
        return len(rows)

    def start_pipeline_job(
        self,
        name: str,
        layer: str,
        parameters: dict[str, object],
        steps_total: int,
        job_id: str | None = None,
    ) -> str:
        now = utc_now()
        row = {
            "id": job_id or stable_id("pipeline", name, layer, now, json.dumps(parameters, sort_keys=True)),
            "name": name,
            "layer": layer,
            "status": "running",
            "current_step": "",
            "steps_total": max(steps_total, 1),
            "steps_done": 0,
            "progress": 0.0,
            "message": "",
            "error": "",
            "parameters": json.dumps(parameters, ensure_ascii=False, sort_keys=True),
            "started_at": now,
            "updated_at": now,
            "finished_at": "",
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO pipeline_jobs (
                    id, name, layer, status, current_step, steps_total, steps_done,
                    progress, message, error, parameters, started_at, updated_at, finished_at
                )
                VALUES (
                    :id, :name, :layer, :status, :current_step, :steps_total, :steps_done,
                    :progress, :message, :error, :parameters, :started_at, :updated_at, :finished_at
                )
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    current_step = excluded.current_step,
                    steps_total = excluded.steps_total,
                    steps_done = excluded.steps_done,
                    progress = excluded.progress,
                    message = excluded.message,
                    error = excluded.error,
                    updated_at = excluded.updated_at,
                    finished_at = ''
                """,
                row,
            )
        return str(row["id"])

    def update_pipeline_job(
        self,
        job_id: str,
        *,
        current_step: str,
        steps_done: int,
        steps_total: int | None = None,
        message: str = "",
        status: str = "running",
    ) -> None:
        now = utc_now()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT steps_total FROM pipeline_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            total = max(int(steps_total if steps_total is not None else (row["steps_total"] if row else 1)), 1)
            done = max(0, min(steps_done, total))
            progress = round((done / total) * 100, 2)
            conn.execute(
                """
                UPDATE pipeline_jobs
                SET status = ?, current_step = ?, steps_total = ?, steps_done = ?,
                    progress = ?, message = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, current_step, total, done, progress, message, now, job_id),
            )

    def finish_pipeline_job(self, job_id: str, status: str = "success", error: str = "") -> None:
        now = utc_now()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT steps_total FROM pipeline_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            total = max(int(row["steps_total"] if row else 1), 1)
            done = total if status == "success" else int(row["steps_done"] if row else 0)
            progress = 100.0 if status == "success" else round((done / total) * 100, 2)
            conn.execute(
                """
                UPDATE pipeline_jobs
                SET status = ?, steps_done = ?, progress = ?, error = ?,
                    updated_at = ?, finished_at = ?
                WHERE id = ?
                """,
                (status, done, progress, error, now, now, job_id),
            )

    def list_pipeline_jobs(self, limit: int = 8) -> list[dict[str, object]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM pipeline_jobs
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._pipeline_job_summary(row) for row in rows]

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

    def start_ingestion_run(self, source: str, parameters: dict[str, object]) -> IngestionRun:
        started_at = utc_now()
        run = IngestionRun(
            id=stable_id("ingestion", source, started_at, json.dumps(parameters, sort_keys=True)),
            source=source,
            status="running",
            parameters=parameters,
            started_at=started_at,
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO ingestion_runs (
                    id, source, status, parameters, records_read, records_written,
                    error, started_at, finished_at
                )
                VALUES (
                    :id, :source, :status, :parameters, :records_read, :records_written,
                    :error, :started_at, :finished_at
                )
                """,
                self._ingestion_run_to_row(run),
            )
        return run

    def finish_ingestion_run(
        self,
        run_id: str,
        status: str,
        records_read: int,
        records_written: int,
        error: str = "",
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE ingestion_runs
                SET status = ?, records_read = ?, records_written = ?, error = ?, finished_at = ?
                WHERE id = ?
                """,
                (status, records_read, records_written, error, utc_now(), run_id),
            )

    def list_ingestion_runs(self, limit: int = 10) -> list[IngestionRun]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM ingestion_runs
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_ingestion_run(row) for row in rows]

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

    def replace_item_clusters(
        self,
        clusters: Iterable[ItemCluster],
        members: Iterable[ItemClusterMember],
        neighbors: Iterable[ItemNeighbor] | None = None,
    ) -> None:
        cluster_rows = list(clusters)
        member_rows = list(members)
        neighbor_rows = list(neighbors or [])
        with self.connect() as conn:
            conn.execute("DELETE FROM item_neighbors")
            conn.execute("DELETE FROM item_cluster_members")
            conn.execute("DELETE FROM item_clusters")
            conn.executemany(
                """
                INSERT INTO item_clusters (
                    id, label, item_count, avg_unit_price, min_unit_price,
                    max_unit_price, total_value, states, created_at
                )
                VALUES (
                    :id, :label, :item_count, :avg_unit_price, :min_unit_price,
                    :max_unit_price, :total_value, :states, :created_at
                )
                """,
                [self._cluster_to_row(cluster) for cluster in cluster_rows],
            )
            conn.executemany(
                """
                INSERT INTO item_cluster_members (cluster_id, item_id, similarity)
                VALUES (:cluster_id, :item_id, :similarity)
                """,
                [asdict(member) for member in member_rows],
            )
            conn.executemany(
                """
                INSERT INTO item_neighbors (item_id, neighbor_item_id, similarity, rank)
                VALUES (:item_id, :neighbor_item_id, :similarity, :rank)
                """,
                [asdict(neighbor) for neighbor in neighbor_rows],
            )

    def list_item_clusters(self, limit: int = 10) -> list[ItemCluster]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM item_clusters
                ORDER BY item_count DESC, total_value DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_cluster(row) for row in rows]

    def cluster_detail(self, cluster_id: str) -> dict[str, object] | None:
        with self.connect() as conn:
            cluster = conn.execute("SELECT * FROM item_clusters WHERE id = ?", (cluster_id,)).fetchone()
            if cluster is None:
                return None
            members = conn.execute(
                """
                SELECT
                    m.similarity,
                    i.id,
                    i.source,
                    i.source_record_id,
                    i.procurement_id,
                    i.item_description,
                    i.unit,
                    i.quantity,
                    i.unit_price,
                    i.total_value,
                    i.currency,
                    i.agency_name,
                    i.supplier_name,
                    i.supplier_id,
                    i.state,
                    i.procurement_date,
                    i.portal_url,
                    i.source_payload
                FROM item_cluster_members m
                JOIN procurement_items i ON i.id = m.item_id
                WHERE m.cluster_id = ?
                ORDER BY i.unit_price DESC, i.total_value DESC
                """,
                (cluster_id,),
            ).fetchall()
        return {
            "cluster": self._cluster_summary(cluster),
            "members": [dict(row) for row in members],
        }

    def item_neighbors(self, item_id: str, limit: int = 10) -> list[dict[str, object]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    n.rank,
                    n.similarity,
                    i.id,
                    i.source,
                    i.source_record_id,
                    i.procurement_id,
                    i.item_description,
                    i.unit,
                    i.quantity,
                    i.unit_price,
                    i.total_value,
                    i.currency,
                    i.agency_name,
                    i.supplier_name,
                    i.supplier_id,
                    i.state,
                    i.procurement_date,
                    i.portal_url
                FROM item_neighbors n
                JOIN procurement_items i ON i.id = n.neighbor_item_id
                WHERE n.item_id = ?
                ORDER BY n.rank ASC
                LIMIT ?
                """,
                (item_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def alert_detail(self, alert_id: str) -> dict[str, object] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    a.id AS alert_id,
                    a.risk_type,
                    a.severity,
                    a.score,
                    a.title,
                    a.explanation,
                    a.genai_explanation,
                    a.evidence,
                    a.created_at,
                    i.id AS item_id,
                    i.source,
                    i.source_record_id,
                    i.procurement_id,
                    i.item_code,
                    i.item_description,
                    i.unit,
                    i.quantity,
                    i.unit_price,
                    i.total_value,
                    i.currency,
                    i.agency_name,
                    i.agency_id,
                    i.supplier_name,
                    i.supplier_id,
                    i.city,
                    i.state,
                    i.procurement_date,
                    i.modality,
                    i.portal_url,
                    i.source_payload
                FROM analysis_alerts a
                JOIN procurement_items i ON i.id = a.item_id
                WHERE a.id = ?
                """,
                (alert_id,),
            ).fetchone()
            if row is None:
                return None
            detail = dict(row)
            detail["evidence"] = json.loads(str(detail["evidence"] or "{}"))
            detail["neighbors"] = self.item_neighbors(str(detail["item_id"]), limit=8)
            detail["description_quality"] = self._description_quality_from_row(row)
            return detail

    def alert_export_rows(self, limit: int | None = None) -> list[dict[str, object]]:
        sql = """
            SELECT
                a.id AS alert_id,
                a.risk_type,
                a.severity,
                a.score,
                a.title,
                a.explanation,
                a.genai_explanation,
                a.evidence,
                a.created_at,
                i.id AS item_id,
                i.source,
                i.source_record_id,
                i.procurement_id,
                i.item_code,
                i.item_description,
                i.unit,
                i.quantity,
                i.unit_price,
                i.total_value,
                i.currency,
                i.agency_name,
                i.agency_id,
                i.supplier_name,
                i.supplier_id,
                i.city,
                i.state,
                i.procurement_date,
                i.modality,
                i.portal_url
            FROM analysis_alerts a
            JOIN procurement_items i ON i.id = a.item_id
            ORDER BY a.severity DESC, a.score DESC, a.created_at DESC
        """
        params: tuple[int, ...] = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        with self.connect() as conn:
            rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
        for row in rows:
            row["evidence"] = json.loads(str(row["evidence"] or "{}"))
        return rows

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
                       i.unit_price, i.total_value, i.procurement_date, i.item_code,
                       i.unit, i.source_payload
                FROM analysis_alerts a
                JOIN procurement_items i ON i.id = a.item_id
                ORDER BY a.severity DESC, a.score DESC
                LIMIT 25
                """
            ).fetchall()
            cluster_totals = conn.execute(
                """
                SELECT
                    COUNT(*) AS clusters,
                    COALESCE(SUM(item_count), 0) AS clustered_items,
                    (SELECT COUNT(*) FROM item_neighbors) AS neighbor_edges
                FROM item_clusters
                """
            ).fetchone()
            top_clusters = conn.execute(
                """
                SELECT * FROM item_clusters
                ORDER BY item_count DESC, total_value DESC
                LIMIT 8
                """
            ).fetchall()
            ingestion_runs = conn.execute(
                """
                SELECT * FROM ingestion_runs
                ORDER BY started_at DESC
                LIMIT 6
                """
            ).fetchall()
            bronze = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN silver_status = 'pending' THEN 1 ELSE 0 END) AS pending,
                    SUM(CASE WHEN silver_status = 'silvered' THEN 1 ELSE 0 END) AS silvered,
                    SUM(CASE WHEN silver_status = 'failed' THEN 1 ELSE 0 END) AS failed
                FROM bronze_records
                """
            ).fetchone()
            golden = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN comparable = 1 THEN 1 ELSE 0 END) AS comparable,
                    SUM(CASE WHEN quality_level = 'generic' THEN 1 ELSE 0 END) AS generic,
                    SUM(CASE WHEN quality_level = 'missing' THEN 1 ELSE 0 END) AS missing,
                    SUM(CASE WHEN quality_level = 'weak' THEN 1 ELSE 0 END) AS weak,
                    SUM(CASE WHEN quality_level = 'usable' THEN 1 ELSE 0 END) AS usable
                FROM golden_items
                """
            ).fetchone()
        return {
            "totals": dict(totals),
            "alerts": dict(alerts),
            "risk_types": [dict(row) for row in risk_types],
            "top_alerts": [self._alert_summary(row) for row in top_alerts],
            "cluster_totals": dict(cluster_totals),
            "top_clusters": [self._cluster_summary(row) for row in top_clusters],
            "ingestion_runs": [self._ingestion_run_summary(row) for row in ingestion_runs],
            "layers": {
                "bronze": self._none_to_zero(dict(bronze)),
                "silver": {"total": int(totals["items"] or 0)},
                "golden": self._none_to_zero(dict(golden)),
            },
            "pipeline_jobs": self.list_pipeline_jobs(limit=6),
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

    @staticmethod
    def _ingestion_run_to_row(run: IngestionRun) -> dict[str, object]:
        row = asdict(run)
        row["parameters"] = json.dumps(run.parameters, ensure_ascii=False, sort_keys=True)
        return row

    @staticmethod
    def _row_to_ingestion_run(row: sqlite3.Row) -> IngestionRun:
        data = dict(row)
        data["parameters"] = json.loads(data["parameters"] or "{}")
        return IngestionRun(**data)

    @staticmethod
    def _cluster_to_row(cluster: ItemCluster) -> dict[str, object]:
        row = asdict(cluster)
        row["states"] = json.dumps(cluster.states, ensure_ascii=False)
        return row

    @staticmethod
    def _row_to_cluster(row: sqlite3.Row) -> ItemCluster:
        data = dict(row)
        data["states"] = json.loads(data["states"] or "[]")
        return ItemCluster(**data)

    @staticmethod
    def _cluster_summary(row: sqlite3.Row) -> dict[str, object]:
        data = dict(row)
        data["states"] = json.loads(data["states"] or "[]")
        return data

    @staticmethod
    def _ingestion_run_summary(row: sqlite3.Row) -> dict[str, object]:
        data = dict(row)
        data["parameters"] = json.loads(data["parameters"] or "{}")
        return data

    @staticmethod
    def _alert_summary(row: sqlite3.Row) -> dict[str, object]:
        data = dict(row)
        data["description_quality"] = Storage._description_quality_from_row(row)
        data.pop("source_payload", None)
        return data

    @staticmethod
    def _description_quality_from_row(row: sqlite3.Row) -> dict[str, object]:
        data = dict(row)
        payload = data.get("source_payload") or "{}"
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        item = ProcurementItem(
            id=str(data.get("item_id") or data.get("id") or ""),
            source=str(data.get("source") or ""),
            source_record_id=str(data.get("source_record_id") or ""),
            procurement_id=str(data.get("procurement_id") or ""),
            item_code=str(data.get("item_code") or ""),
            item_description=str(data.get("item_description") or ""),
            unit=str(data.get("unit") or ""),
            quantity=float(data.get("quantity") or 0),
            unit_price=float(data.get("unit_price") or 0),
            total_value=float(data.get("total_value") or 0),
            currency=str(data.get("currency") or "BRL"),
            agency_name=str(data.get("agency_name") or ""),
            agency_id=str(data.get("agency_id") or ""),
            supplier_name=str(data.get("supplier_name") or ""),
            supplier_id=str(data.get("supplier_id") or ""),
            city=str(data.get("city") or ""),
            state=str(data.get("state") or ""),
            procurement_date=str(data.get("procurement_date") or ""),
            modality=str(data.get("modality") or ""),
            portal_url=str(data.get("portal_url") or ""),
            source_payload=payload if isinstance(payload, dict) else {},
        )
        return description_quality(item)

    @staticmethod
    def _bronze_record_to_row(
        source: str,
        record: dict[str, object],
        parameters: dict[str, object],
    ) -> dict[str, object]:
        source_record_id = ""
        procurement_id = ""
        item_number = ""
        record_date = ""
        if source == "pncp":
            source_record_id = str(record.get("numeroControlePNCP") or stable_id(record))
            procurement_id = source_record_id
            item_number = str(record.get("numeroCompra") or "")
            record_date = str(record.get("dataPublicacaoPncp") or record.get("dataInclusao") or "")[:10]
        elif source == "compras_gov":
            source_record_id = str(record.get("idCompraItem") or record.get("idContratacaoPNCP") or stable_id(record))
            procurement_id = str(record.get("idContratacaoPNCP") or record.get("idCompra") or "")
            item_number = str(record.get("numeroItemPncp") or record.get("idCompraItem") or "")
            record_date = str(record.get("dataResultadoPncp") or record.get("dataInclusaoPncp") or "")[:10]
        else:
            source_record_id = stable_id(record)
        return {
            "id": stable_id("bronze", source, source_record_id),
            "source": source,
            "source_record_id": source_record_id,
            "procurement_id": procurement_id,
            "item_number": item_number,
            "record_date": record_date,
            "payload": json.dumps(record, ensure_ascii=False, sort_keys=True),
            "parameters": json.dumps(parameters, ensure_ascii=False, sort_keys=True),
            "silver_status": "pending",
            "silver_error": "",
            "collected_at": utc_now(),
        }

    @staticmethod
    def _bronze_row_to_dict(row: sqlite3.Row) -> dict[str, object]:
        data = dict(row)
        data["payload"] = json.loads(data["payload"] or "{}")
        data["parameters"] = json.loads(data["parameters"] or "{}")
        return data

    @staticmethod
    def _pipeline_job_summary(row: sqlite3.Row) -> dict[str, object]:
        data = dict(row)
        data["parameters"] = json.loads(data["parameters"] or "{}")
        return data

    @staticmethod
    def _none_to_zero(data: dict[str, object]) -> dict[str, object]:
        return {key: (0 if value is None else value) for key, value in data.items()}
