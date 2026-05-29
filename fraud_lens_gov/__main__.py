from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

from .anomalies import analyze_items
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

    pncp = sub.add_parser("ingest-pncp", help="Ingest contracting notices from the PNCP public API.")
    pncp.add_argument("--start", required=False, help="Start date in YYYYMMDD format.")
    pncp.add_argument("--end", required=False, help="End date in YYYYMMDD format.")
    pncp.add_argument("--modality", type=int, default=6, help="PNCP modality code. Default: 6.")
    pncp.add_argument("--page-size", type=int, default=10, help="Page size. Default: 10.")
    pncp.add_argument("--analyze", action="store_true", help="Run anomaly analysis after ingesting.")

    compras = sub.add_parser("ingest-compras", help="Ingest item award results from Compras.gov.br open data.")
    compras.add_argument("--start", required=False, help="Start date in YYYY-MM-DD format.")
    compras.add_argument("--end", required=False, help="End date in YYYY-MM-DD format.")
    compras.add_argument("--page-size", type=int, default=10, help="Page size. Compras.gov.br requires 10-500.")
    compras.add_argument("--analyze", action="store_true", help="Run anomaly analysis after ingesting.")

    google = sub.add_parser("discover-portals", help="Use Google Programmable Search to discover local portals.")
    google.add_argument("query", help="Search query, e.g. 'portal transparencia licitacoes site:sp.gov.br'.")
    google.add_argument("--site", help="Optional site restriction.")
    google.add_argument("--limit", type=int, default=10, help="Maximum result count.")

    sub.add_parser("analyze", help="Run statistical anomaly detection over stored items.")

    genai = sub.add_parser("explain-alerts", help="Use OpenAI Responses API to enrich alert explanations.")
    genai.add_argument("--limit", type=int, default=10, help="Maximum alerts to enrich.")

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
        count = storage.upsert_items(SAMPLE_ITEMS)
        print(f"Loaded {count} sample items.")
        if args.analyze:
            print(f"Generated {_analyze(storage)} alerts.")
        return 0

    if command == "ingest-pncp":
        start, end = args.start, args.end
        if not start or not end:
            start, end = _default_pncp_window()
        client = PncpClient()
        items = client.fetch_contracting_notices(start, end, args.modality, args.page_size)
        count = storage.upsert_items(items)
        print(f"Loaded {count} PNCP records for {start}..{end}.")
        if args.analyze:
            print(f"Generated {_analyze(storage)} alerts.")
        return 0

    if command == "ingest-compras":
        start, end = args.start, args.end
        if not start or not end:
            start, end = _default_iso_window()
        client = ComprasGovClient()
        items = client.fetch_awarded_items(start, end, args.page_size)
        count = storage.upsert_items(items)
        print(f"Loaded {count} Compras.gov.br records for {start}..{end}.")
        if args.analyze:
            print(f"Generated {_analyze(storage)} alerts.")
        return 0

    if command == "discover-portals":
        client = GoogleProgrammableSearchClient.from_env()
        results = client.search(args.query, site=args.site, limit=args.limit)
        for result in results:
            print(f"- {result['title']}: {result['link']}")
        return 0

    if command == "analyze":
        print(f"Generated {_analyze(storage)} alerts.")
        return 0

    if command == "explain-alerts":
        alerts = storage.list_alerts(limit=args.limit)
        updated = enrich_alerts_with_genai(alerts)
        storage.update_alert_explanations(updated)
        print(f"Enriched {len(updated)} alerts.")
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
