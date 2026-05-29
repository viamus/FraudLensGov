from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from .anomalies import analyze_items
from .clustering import build_cluster_index
from .exporting import export_alerts
from .genai import enrich_alerts_with_genai
from .normalization import from_compras_award, from_pncp_notice
from .sample_data import SAMPLE_ITEMS
from .sources.compras_gov import ComprasGovClient
from .sources.google_search import GoogleProgrammableSearchClient
from .sources.pncp import PncpClient
from .storage import Storage


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

    backfill = sub.add_parser("backfill", help="Backfill public data in date windows.")
    backfill.add_argument("--source", choices=["both", "pncp", "compras"], default="both")
    backfill.add_argument("--start", help="Start date in YYYY-MM-DD format. Default: 10 years ago.")
    backfill.add_argument("--end", help="End date in YYYY-MM-DD format. Default: today.")
    backfill.add_argument("--window-days", type=int, default=30, help="Date window size. Default: 30.")
    backfill.add_argument("--max-pages", type=int, default=1, help="Maximum pages per window/source.")
    backfill.add_argument("--pncp-page-size", type=int, default=50, help="PNCP page size.")
    backfill.add_argument("--compras-page-size", type=int, default=10, help="Compras.gov.br page size.")
    backfill.add_argument("--modality", type=int, default=6, help="PNCP modality code. Default: 6.")
    backfill.add_argument("--analyze", action="store_true", help="Run anomaly analysis after the backfill.")
    backfill.add_argument("--cluster", action="store_true", help="Build item clusters after the backfill.")

    bronze = sub.add_parser("backfill-bronze", help="Backfill raw public records into the Bronze layer.")
    bronze.add_argument("--source", choices=["both", "pncp", "compras"], default="both")
    bronze.add_argument("--start", help="Start date in YYYY-MM-DD format. Default: 10 years ago.")
    bronze.add_argument("--end", help="End date in YYYY-MM-DD format. Default: today.")
    bronze.add_argument("--window-days", type=int, default=30, help="Date window size. Default: 30.")
    bronze.add_argument("--max-pages", type=int, default=1, help="Maximum pages per window/source.")
    bronze.add_argument("--pncp-page-size", type=int, default=50, help="PNCP page size.")
    bronze.add_argument("--compras-page-size", type=int, default=10, help="Compras.gov.br page size.")
    bronze.add_argument("--modality", type=int, default=6, help="PNCP modality code. Default: 6.")
    bronze.add_argument("--async", dest="run_async", action="store_true", help="Run in a background process.")
    bronze.add_argument("--job-id", help=argparse.SUPPRESS)

    silver = sub.add_parser("build-silver", help="Normalize Bronze records and enrich item metadata.")
    silver.add_argument("--source", choices=["both", "pncp", "compras_gov"], default="both")
    silver.add_argument("--limit", type=int, help="Maximum pending Bronze records to process.")
    silver.add_argument("--skip-enrichment", action="store_true", help="Normalize without calling complementary APIs.")
    silver.add_argument("--async", dest="run_async", action="store_true", help="Run in a background process.")
    silver.add_argument("--job-id", help=argparse.SUPPRESS)

    golden = sub.add_parser("build-golden", help="Build the Golden layer and optionally run analysis.")
    golden.add_argument("--analyze", action="store_true", help="Run anomaly analysis after building Golden.")
    golden.add_argument("--cluster", action="store_true", help="Build item clusters after building Golden.")
    golden.add_argument("--k", type=int, default=8, help="Number of nearest neighbors per item.")
    golden.add_argument("--min-similarity", type=float, default=0.42, help="Minimum neighbor similarity.")
    golden.add_argument("--limit", type=int, help="Maximum stale items to materialize in this run.")
    golden.add_argument("--full-refresh", action="store_true", help="Rebuild every Golden row instead of only stale items.")
    golden.add_argument("--async", dest="run_async", action="store_true", help="Run in a background process.")
    golden.add_argument("--job-id", help=argparse.SUPPRESS)

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
    web.add_argument("--legacy-webapp", action="store_true", help="Run the pre-Django prototype web server.")

    return parser


def _default_pncp_window() -> tuple[str, str]:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=1)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _default_iso_window() -> tuple[str, str]:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=1)
    return start.isoformat(), end.isoformat()


def _default_ten_year_window() -> tuple[date, date]:
    end = date.today()
    try:
        start = end.replace(year=end.year - 10)
    except ValueError:
        start = end.replace(month=2, day=28, year=end.year - 10)
    return start, end


def _parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


def _date_windows(start: date, end: date, window_days: int) -> list[tuple[date, date]]:
    if start > end:
        raise ValueError("start date must be before or equal to end date")
    window_days = max(1, window_days)
    windows: list[tuple[date, date]] = []
    current = start
    while current <= end:
        current_end = min(current + timedelta(days=window_days - 1), end)
        windows.append((current, current_end))
        current = current_end + timedelta(days=1)
    return windows


def _source_count(source: str) -> int:
    return 2 if source == "both" else 1


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
    clusters, members, neighbors = build_cluster_index(storage.list_items(), k=k, min_similarity=min_similarity)
    storage.replace_item_clusters(clusters, members, neighbors)
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


def _ingest_items_with_run(
    storage: Storage,
    source: str,
    params: dict[str, object],
    items_factory,
) -> tuple[int, int, bool]:
    run = storage.start_ingestion_run(source, params)
    try:
        items = items_factory()
        count = storage.upsert_items(items)
    except Exception as exc:
        _finish_ingestion(storage, run.id, "failed", 0, 0, str(exc))
        print(f"Failed {source} {params}: {exc}")
        return 0, 0, False
    _finish_ingestion(storage, run.id, "success", len(items), count)
    return len(items), count, True


def _launch_async(args: argparse.Namespace, command: str, command_args: list[str], job_id: str) -> None:
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{job_id}.log"
    cmd = [
        sys.executable,
        "-m",
        "fraud_lens_gov",
        "--db",
        str(args.db),
        command,
        *command_args,
        "--job-id",
        job_id,
    ]
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP") else 0
    log_file = log_path.open("ab")
    try:
        subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, creationflags=creationflags)
    finally:
        log_file.close()
    print(f"Started background job {job_id}. Progress: /api/summary. Log: {log_path}")


def _build_bronze_cli_args(args: argparse.Namespace, start_date: date, end_date: date) -> list[str]:
    return [
        "--source",
        str(args.source),
        "--start",
        start_date.isoformat(),
        "--end",
        end_date.isoformat(),
        "--window-days",
        str(args.window_days),
        "--max-pages",
        str(args.max_pages),
        "--pncp-page-size",
        str(args.pncp_page_size),
        "--compras-page-size",
        str(args.compras_page_size),
        "--modality",
        str(args.modality),
    ]


def _build_silver_cli_args(args: argparse.Namespace) -> list[str]:
    result = ["--source", str(args.source)]
    if args.limit is not None:
        result.extend(["--limit", str(args.limit)])
    if args.skip_enrichment:
        result.append("--skip-enrichment")
    return result


def _build_golden_cli_args(args: argparse.Namespace) -> list[str]:
    result = ["--k", str(args.k), "--min-similarity", str(args.min_similarity)]
    if args.limit is not None:
        result.extend(["--limit", str(args.limit)])
    if args.full_refresh:
        result.append("--full-refresh")
    if args.analyze:
        result.append("--analyze")
    if args.cluster:
        result.append("--cluster")
    return result


def _serve_django(db_path: str, host: str, port: int) -> None:
    os.environ["FRAUDLENS_DB"] = str(Path(db_path).resolve())
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fraudlensgov_site.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise SystemExit("Django is required. Install pinned dependencies with: python -m pip install -r requirements.txt") from exc
    execute_from_command_line(["manage.py", "runserver", f"{host}:{port}", "--noreload"])


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

    if command == "backfill-bronze":
        default_start, default_end = _default_ten_year_window()
        start_date = _parse_iso_date(args.start) if args.start else default_start
        end_date = _parse_iso_date(args.end) if args.end else default_end
        windows = _date_windows(start_date, end_date, args.window_days)
        steps_total = len(windows) * _source_count(args.source)
        params = {
            "source": args.source,
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "window_days": args.window_days,
            "max_pages": args.max_pages,
            "pncp_page_size": args.pncp_page_size,
            "compras_page_size": args.compras_page_size,
            "modality": args.modality,
        }
        if args.run_async and not args.job_id:
            job_id = storage.start_pipeline_job("Backfill Bronze", "bronze", params, steps_total)
            _launch_async(args, "backfill-bronze", _build_bronze_cli_args(args, start_date, end_date), job_id)
            return 0

        job_id = args.job_id or storage.start_pipeline_job("Backfill Bronze", "bronze", params, steps_total)
        pncp = PncpClient()
        compras_client = ComprasGovClient()
        totals = {"read": 0, "written": 0, "failed": 0}
        step_done = 0
        print(f"Bronze backfill {args.source}: {start_date.isoformat()}..{end_date.isoformat()} in {len(windows)} windows")
        try:
            for window_start, window_end in windows:
                if args.source in {"both", "pncp"}:
                    step = f"PNCP {window_start.isoformat()}..{window_end.isoformat()}"
                    storage.update_pipeline_job(job_id, current_step=step, steps_done=step_done, steps_total=steps_total)
                    params_step = {
                        **params,
                        "start": window_start.strftime("%Y%m%d"),
                        "end": window_end.strftime("%Y%m%d"),
                        "source": "pncp",
                    }
                    try:
                        records = pncp.fetch_contracting_notice_records(
                            params_step["start"],
                            params_step["end"],
                            args.modality,
                            args.pncp_page_size,
                            max_pages=args.max_pages,
                        )
                        totals["read"] += len(records)
                        totals["written"] += storage.upsert_bronze_records("pncp", records, params_step)
                    except Exception as exc:
                        totals["failed"] += 1
                        print(f"Failed {step}: {exc}")
                    step_done += 1
                    storage.update_pipeline_job(
                        job_id,
                        current_step=step,
                        steps_done=step_done,
                        steps_total=steps_total,
                        message=f"{totals['written']} Bronze records stored",
                    )
                    print(f"{step_done}/{steps_total} Bronze steps ({(step_done / steps_total) * 100:.1f}%)")

                if args.source in {"both", "compras"}:
                    step = f"Compras.gov.br {window_start.isoformat()}..{window_end.isoformat()}"
                    storage.update_pipeline_job(job_id, current_step=step, steps_done=step_done, steps_total=steps_total)
                    params_step = {
                        **params,
                        "start": window_start.isoformat(),
                        "end": window_end.isoformat(),
                        "source": "compras_gov",
                    }
                    try:
                        records = compras_client.fetch_awarded_item_records(
                            params_step["start"],
                            params_step["end"],
                            args.compras_page_size,
                            max_pages=args.max_pages,
                        )
                        totals["read"] += len(records)
                        totals["written"] += storage.upsert_bronze_records("compras_gov", records, params_step)
                    except Exception as exc:
                        totals["failed"] += 1
                        print(f"Failed {step}: {exc}")
                    step_done += 1
                    storage.update_pipeline_job(
                        job_id,
                        current_step=step,
                        steps_done=step_done,
                        steps_total=steps_total,
                        message=f"{totals['written']} Bronze records stored",
                    )
                    print(f"{step_done}/{steps_total} Bronze steps ({(step_done / steps_total) * 100:.1f}%)")
        except Exception as exc:
            storage.finish_pipeline_job(job_id, "failed", str(exc))
            raise
        status = "success" if totals["failed"] == 0 else "partial"
        storage.finish_pipeline_job(job_id, status, "" if status == "success" else f"{totals['failed']} windows failed")
        print(
            "Bronze complete: "
            f"{totals['read']} read, {totals['written']} stored, {totals['failed']} failed windows."
        )
        return 0

    if command == "build-silver":
        source = args.source
        pending = storage.bronze_records_for_silver(source=source, limit=args.limit)
        steps_total = len(pending) or 1
        params = {
            "source": source,
            "limit": args.limit,
            "skip_enrichment": args.skip_enrichment,
        }
        if args.run_async and not args.job_id:
            job_id = storage.start_pipeline_job("Build Silver", "silver", params, steps_total)
            _launch_async(args, "build-silver", _build_silver_cli_args(args), job_id)
            return 0

        job_id = args.job_id or storage.start_pipeline_job("Build Silver", "silver", params, steps_total)
        if not pending:
            storage.update_pipeline_job(job_id, current_step="Silver up to date", steps_done=1, steps_total=1)
            storage.finish_pipeline_job(job_id, "success")
            print("Silver is up to date: no pending Bronze records.")
            return 0

        compras_client = ComprasGovClient()
        written = 0
        failed = 0
        print(f"Silver build: {len(pending)} pending Bronze records")
        for index, row in enumerate(pending, start=1):
            step = f"{row['source']} {row['source_record_id']}"
            storage.update_pipeline_job(job_id, current_step=step, steps_done=index - 1, steps_total=steps_total)
            bronze_id = str(row["id"])
            try:
                payload = dict(row["payload"])
                if row["source"] == "compras_gov":
                    if not args.skip_enrichment:
                        payload = compras_client.enrich_award_record(payload)
                    item = from_compras_award(payload)
                elif row["source"] == "pncp":
                    item = from_pncp_notice(payload)
                else:
                    raise ValueError(f"Unsupported Bronze source: {row['source']}")
                storage.upsert_items([item])
                storage.mark_bronze_silver_status([bronze_id], "silvered")
                written += 1
            except Exception as exc:
                failed += 1
                storage.mark_bronze_silver_status([bronze_id], "failed", str(exc))
                print(f"Failed Silver {step}: {exc}")
            storage.update_pipeline_job(
                job_id,
                current_step=step,
                steps_done=index,
                steps_total=steps_total,
                message=f"{written} Silver items written",
            )
            if index == 1 or index == steps_total or index % 25 == 0:
                print(f"{index}/{steps_total} Silver records ({(index / steps_total) * 100:.1f}%)")
        status = "success" if failed == 0 else "partial"
        storage.finish_pipeline_job(job_id, status, "" if status == "success" else f"{failed} records failed")
        print(f"Silver complete: {written} written, {failed} failed.")
        return 0

    if command == "build-golden":
        steps_total = 1 + int(bool(args.analyze)) + int(bool(args.cluster))
        stale_count = storage.count_items() if args.full_refresh else storage.count_stale_golden_items()
        params = {
            "analyze": args.analyze,
            "cluster": args.cluster,
            "full_refresh": args.full_refresh,
            "limit": args.limit,
            "k": args.k,
            "min_similarity": args.min_similarity,
            "stale_items": stale_count,
        }
        if args.run_async and not args.job_id:
            job_id = storage.start_pipeline_job("Build Golden", "golden", params, steps_total)
            _launch_async(args, "build-golden", _build_golden_cli_args(args), job_id)
            return 0

        job_id = args.job_id or storage.start_pipeline_job("Build Golden", "golden", params, steps_total)
        step_done = 0
        try:
            storage.update_pipeline_job(job_id, current_step="Golden materialization", steps_done=step_done, steps_total=steps_total)
            if args.full_refresh:
                golden_count = storage.replace_golden_items(storage.list_items())
                materialization_mode = "full refresh"
            else:
                stale_items = storage.stale_golden_items(limit=args.limit)
                golden_count = storage.upsert_golden_items(stale_items)
                materialization_mode = "incremental"
            step_done += 1
            storage.update_pipeline_job(
                job_id,
                current_step="Golden materialization",
                steps_done=step_done,
                steps_total=steps_total,
                message=f"{golden_count} Golden records built ({materialization_mode})",
            )
            print(f"Golden materialized: {golden_count} records ({materialization_mode}).")
            if args.analyze:
                storage.update_pipeline_job(job_id, current_step="Global risk analysis", steps_done=step_done, steps_total=steps_total)
                alert_count = _analyze(storage)
                step_done += 1
                storage.update_pipeline_job(
                    job_id,
                    current_step="Global risk analysis",
                    steps_done=step_done,
                    steps_total=steps_total,
                    message=f"{alert_count} alerts generated",
                )
                print(f"Generated {alert_count} alerts.")
            if args.cluster:
                storage.update_pipeline_job(job_id, current_step="KNN clusters", steps_done=step_done, steps_total=steps_total)
                cluster_count, member_count = _build_clusters(storage, k=args.k, min_similarity=args.min_similarity)
                step_done += 1
                storage.update_pipeline_job(
                    job_id,
                    current_step="KNN clusters",
                    steps_done=step_done,
                    steps_total=steps_total,
                    message=f"{cluster_count} clusters, {member_count} memberships",
                )
                print(f"Built {cluster_count} clusters with {member_count} item memberships.")
        except Exception as exc:
            storage.finish_pipeline_job(job_id, "failed", str(exc))
            raise
        storage.finish_pipeline_job(job_id, "success")
        return 0

    if command == "backfill":
        default_start, default_end = _default_ten_year_window()
        start_date = _parse_iso_date(args.start) if args.start else default_start
        end_date = _parse_iso_date(args.end) if args.end else default_end
        windows = _date_windows(start_date, end_date, args.window_days)
        pncp = PncpClient()
        compras_client = ComprasGovClient()
        totals = {"read": 0, "written": 0, "success": 0, "failed": 0}
        print(f"Backfill {args.source}: {start_date.isoformat()}..{end_date.isoformat()} in {len(windows)} windows")
        for window_start, window_end in windows:
            if args.source in {"both", "pncp"}:
                pncp_start = window_start.strftime("%Y%m%d")
                pncp_end = window_end.strftime("%Y%m%d")
                params = {
                    "start": pncp_start,
                    "end": pncp_end,
                    "modality": args.modality,
                    "page_size": args.pncp_page_size,
                    "max_pages": args.max_pages,
                    "backfill": True,
                }
                read, written, ok = _ingest_items_with_run(
                    storage,
                    "pncp",
                    params,
                    lambda pncp_start=pncp_start, pncp_end=pncp_end: pncp.fetch_contracting_notices(
                        pncp_start,
                        pncp_end,
                        args.modality,
                        args.pncp_page_size,
                        max_pages=args.max_pages,
                    ),
                )
                totals["read"] += read
                totals["written"] += written
                totals["success" if ok else "failed"] += 1
            if args.source in {"both", "compras"}:
                iso_start = window_start.isoformat()
                iso_end = window_end.isoformat()
                params = {
                    "start": iso_start,
                    "end": iso_end,
                    "page_size": args.compras_page_size,
                    "max_pages": args.max_pages,
                    "backfill": True,
                }
                read, written, ok = _ingest_items_with_run(
                    storage,
                    "compras_gov",
                    params,
                    lambda iso_start=iso_start, iso_end=iso_end: compras_client.fetch_awarded_items(
                        iso_start,
                        iso_end,
                        args.compras_page_size,
                        max_pages=args.max_pages,
                    ),
                )
                totals["read"] += read
                totals["written"] += written
                totals["success" if ok else "failed"] += 1
        print(
            "Backfill complete: "
            f"{totals['read']} read, {totals['written']} written, "
            f"{totals['success']} successful source-windows, {totals['failed']} failed."
        )
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
        if args.legacy_webapp:
            from .webapp import serve as serve_legacy

            serve_legacy(storage, host=args.host, port=args.port)
        else:
            _serve_django(args.db, args.host, args.port)
        return 0

    raise SystemExit(f"Unknown command: {command}")


if __name__ == "__main__":
    raise SystemExit(main())
