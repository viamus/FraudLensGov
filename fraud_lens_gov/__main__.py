from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

from .anomalies import analyze_items
from .clustering import build_item_clusters
from .exporting import export_alerts
from .genai import enrich_alerts_with_genai
from .sample_data import SAMPLE_ITEMS
from .sources.compras_gov import ComprasGovClient
from .sources.google_search import GoogleProgrammableSearchClient
from .sources.pncp import PncpClient
from .storage import Storage
from .webapp import serve


DEFAULT_DB = Path("data/fraudlens.sqlite")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fraud-lens-gov",
        description="Ingest public procurement data, detect risk signals, and serve a local dashboard.",
    )
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path.")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init-db", help="Create database schema.")
    sub.add_parser("reset-db", help="Delete local database and create a fresh schema.")

    sample = sub.add_parser("ingest-sample", help="Load deterministic sample procurement items.")
    sample.add_argument("--analyze", action="store_true", help="Run anomaly analysis after ingesting.")
    sample.add_argument("--cluster", action="store_true", help="Build item clusters after ingesting.")

    pncp = sub.add_parser("ingest-pncp", help="Ingest contracting notices from the PNCP public API.")
    pncp.add_argument("--start", required=False, help="Start date in YYYYMMDD format.")
    pncp.add_argument("--end", required=False, help="End date in YYYYMMDD format.")
    pncp.add_argument("--modality", type=int, default=6, help="PNCP modality code. Default: 6.")
    pncp.add_argument("--page-size", type=int, default=10, help="Page size. Default: 10.")
    pncp.add_argument("--max-pages", type=int, default=1, help="Maximum pages to fetch. Default: 1.")
    pncp.add_argument("--analyze", action="store_true", help="Run anomaly analysis after ingesting.")
    pncp.add_argument("--cluster", action="store_true", help="Build item clusters after ingesting.")

    compras = sub.add_parser("ingest-compras", help="Ingest item award results from Compras.gov.br open data.")
    compras.add_argument("--start", required=False, help="Start date in YYYY-MM-DD format.")
    compras.add_argument("--end", required=False, help="End date in YYYY-MM-DD format.")
    compras.add_argument("--page-size", type=int, default=10, help="Page size. Compras.gov.br requires 10-500.")
    compras.add_argument("--max-pages", type=int, default=1, help="Maximum pages to fetch. Default: 1.")
    compras.add_argument("--analyze", action="store_true", help="Run anomaly analysis after ingesting.")
    compras.add_argument("--cluster", action="store_true", help="Build item clusters after ingesting.")

    google = sub.add_parser("discover-portals", help="Use Google Programmable Search to discover local portals.")
    google.add_argument("query", help="Search query, e.g. 'portal transparencia licitacoes site:sp.gov.br'.")
    google.add_argument("--site", help="Optional site restriction.")
    google.add_argument("--limit", type=int, default=10, help="Maximum result count.")

    analyze = sub.add_parser("analyze", help="Run statistical anomaly detection over stored items.")
    analyze.add_argument("--cluster", action="store_true", help="Build item clusters after analyzing.")

    clusters = sub.add_parser("build-clusters", help="Build KNN-style lexical item clusters.")
    clusters.add_argument("--k", type=int, default=8, help="Number of nearest neighbors per item.")
    clusters.add_argument("--min-similarity", type=float, default=0.42, help="Minimum neighbor similarity.")

    genai = sub.add_parser("explain-alerts", help="Use OpenAI Responses API to enrich alert explanations.")
    genai.add_argument("--limit", type=int, default=10, help="Maximum alerts to enrich.")

    export = sub.add_parser("export-alerts", help="Export joined alert evidence for audit review.")
    export.add_argument("--format", choices=["json", "csv", "md"], default="md")
    export.add_argument("--output", help="Output path. Default: reports/alerts.<format>.")
    export.add_argument("--limit", type=int, help="Maximum alerts to export.")

    web = sub.add_parser("serve", help="Run the local dashboard.")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8080)
    web.add_argument("--bootstrap-sample", action="store_true", help="Load sample data if the database is empty.")

    return parser


def _default_pncp_window() -> tuple[str, str]:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=1)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _default_iso_window() -> tuple[str, str]:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=1)
    return start.isoformat(), end.isoformat()


def _storage(db_path: str) -> Storage:
    storage = Storage(Path(db_path))
    storage.init_schema()
    return storage


def _analyze(storage: Storage) -> int:
    items = storage.list_items()
    alerts = analyze_items(items)
    storage.replace_alerts(alerts)
    return len(alerts)


def _build_clusters(storage: Storage, k: int = 8, min_similarity: float = 0.42) -> tuple[int, int]:
    clusters, members = build_item_clusters(storage.list_items(), k=k, min_similarity=min_similarity)
    storage.replace_item_clusters(clusters, members)
    return len(clusters), len(members)


def _finish_ingestion(
    storage: Storage,
    run_id: str,
    status: str,
    records_read: int,
    records_written: int,
    error: str = "",
) -> None:
    storage.finish_ingestion_run(
        run_id,
        status=status,
        records_read=records_read,
        records_written=records_written,
        error=error,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "serve"

    if command == "reset-db":
        db_path = Path(args.db)
        if db_path.exists():
            db_path.unlink()
        storage = _storage(args.db)
        print(f"Fresh database created at {storage.db_path}")
        return 0

    storage = _storage(args.db)

    if command == "init-db":
        print(f"Database ready at {storage.db_path}")
        return 0

    if command == "ingest-sample":
        params = {"records": len(SAMPLE_ITEMS), "analyze": args.analyze, "cluster": args.cluster}
        run = storage.start_ingestion_run("sample", params)
        count = storage.upsert_items(SAMPLE_ITEMS)
        _finish_ingestion(storage, run.id, "success", len(SAMPLE_ITEMS), count)
        print(f"Loaded {count} sample items.")
        if args.analyze:
            print(f"Generated {_analyze(storage)} alerts.")
        if args.cluster:
            cluster_count, member_count = _build_clusters(storage)
            print(f"Built {cluster_count} clusters with {member_count} item memberships.")
        return 0

    if command == "ingest-pncp":
        start, end = args.start, args.end
        if not start or not end:
            start, end = _default_pncp_window()
        client = PncpClient()
        params = {
            "start": start,
            "end": end,
            "modality": args.modality,
            "page_size": args.page_size,
            "max_pages": args.max_pages,
            "analyze": args.analyze,
            "cluster": args.cluster,
        }
        run = storage.start_ingestion_run("pncp", params)
        try:
            items = client.fetch_contracting_notices(
                start,
                end,
                args.modality,
                args.page_size,
                max_pages=args.max_pages,
            )
            count = storage.upsert_items(items)
        except Exception as exc:
            _finish_ingestion(storage, run.id, "failed", 0, 0, str(exc))
            raise
        _finish_ingestion(storage, run.id, "success", len(items), count)
        print(f"Loaded {count} PNCP records for {start}..{end}.")
        if args.analyze:
            print(f"Generated {_analyze(storage)} alerts.")
        if args.cluster:
            cluster_count, member_count = _build_clusters(storage)
            print(f"Built {cluster_count} clusters with {member_count} item memberships.")
        return 0

    if command == "ingest-compras":
        start, end = args.start, args.end
        if not start or not end:
            start, end = _default_iso_window()
        client = ComprasGovClient()
        params = {
            "start": start,
            "end": end,
            "page_size": args.page_size,
            "max_pages": args.max_pages,
            "analyze": args.analyze,
            "cluster": args.cluster,
        }
        run = storage.start_ingestion_run("compras_gov", params)
        try:
            items = client.fetch_awarded_items(start, end, args.page_size, max_pages=args.max_pages)
            count = storage.upsert_items(items)
        except Exception as exc:
            _finish_ingestion(storage, run.id, "failed", 0, 0, str(exc))
            raise
        _finish_ingestion(storage, run.id, "success", len(items), count)
        print(f"Loaded {count} Compras.gov.br records for {start}..{end}.")
        if args.analyze:
            print(f"Generated {_analyze(storage)} alerts.")
        if args.cluster:
            cluster_count, member_count = _build_clusters(storage)
            print(f"Built {cluster_count} clusters with {member_count} item memberships.")
        return 0

    if command == "discover-portals":
        client = GoogleProgrammableSearchClient.from_env()
        results = client.search(args.query, site=args.site, limit=args.limit)
        for result in results:
            print(f"- {result['title']}: {result['link']}")
        return 0

    if command == "analyze":
        print(f"Generated {_analyze(storage)} alerts.")
        if args.cluster:
            cluster_count, member_count = _build_clusters(storage)
            print(f"Built {cluster_count} clusters with {member_count} item memberships.")
        return 0

    if command == "build-clusters":
        cluster_count, member_count = _build_clusters(storage, k=args.k, min_similarity=args.min_similarity)
        print(f"Built {cluster_count} clusters with {member_count} item memberships.")
        return 0

    if command == "explain-alerts":
        alerts = storage.list_alerts(limit=args.limit)
        updated = enrich_alerts_with_genai(alerts)
        storage.update_alert_explanations(updated)
        print(f"Enriched {len(updated)} alerts.")
        return 0

    if command == "export-alerts":
        output = Path(args.output) if args.output else Path(f"reports/alerts.{args.format}")
        rows = storage.alert_export_rows(limit=args.limit)
        written = export_alerts(rows, output, args.format)
        print(f"Exported {len(rows)} alerts to {written}")
        return 0

    if command == "serve":
        if args.bootstrap_sample and storage.count_items() == 0:
            storage.upsert_items(SAMPLE_ITEMS)
            _analyze(storage)
        serve(storage, host=args.host, port=args.port)
        return 0

    raise SystemExit(f"Unknown command: {command}")


if __name__ == "__main__":
    raise SystemExit(main())
