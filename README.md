# FraudLensGov

FraudLensGov is an open-source project for reading public procurement and bidding data, organizing it into auditable signals, and using statistical analysis, RAG, and GenAI to highlight potential fraud-risk patterns.

The project helps humans prioritize review. It does not automatically accuse people or organizations of fraud.

## Prototype

The current prototype uses a small, pinned Python stack:

- Public API connectors for PNCP and Compras.gov.br.
- Optional Google Programmable Search discovery for local procurement portals.
- Local SQLite storage for development.
- Bronze/Silver/Golden processing layers with observable pipeline jobs.
- Statistical anomaly detection with an initial nearest-neighbor comparable-price strategy.
- KNN-style lexical clusters persisted locally for comparable item review.
- Unit-aware Golden comparability rules: mass/volume normalization, broad-scope blocking, and specification-required item families.
- Optional OpenAI Responses API explanations.
- Django 5.2 LTS dashboard with a dark operational audit UI.
- Corporate audit shell with collapsible navigation, paginated table-first investigation views, filters, and alert detail pages.
- Legacy standard-library dashboard still available with `--legacy-webapp`.

## Run Locally

Requires Python 3.11+.

```powershell
python -m pip install -r requirements.txt
python -m fraud_lens_gov ingest-sample --analyze --cluster
python -m fraud_lens_gov serve --host 127.0.0.1 --port 8097
```

Open:

```text
http://127.0.0.1:8097
```

Or start with sample bootstrap in one command:

```powershell
python -m fraud_lens_gov serve --bootstrap-sample --host 127.0.0.1 --port 8097
```

## Ingest Public APIs

PNCP:

```powershell
python -m fraud_lens_gov ingest-pncp --start 20240501 --end 20240502 --modality 6 --page-size 10 --max-pages 2 --analyze --cluster
```

Compras.gov.br:

```powershell
python -m fraud_lens_gov ingest-compras --start 2025-09-01 --end 2025-09-02 --page-size 10 --max-pages 1 --analyze --cluster
```

Build clusters again after any manual data change:

```powershell
python -m fraud_lens_gov build-clusters --k 8 --min-similarity 0.42
```

Layered public-data pipeline:

```powershell
python -m fraud_lens_gov backfill-bronze --source compras --start 2026-05-01 --end 2026-05-29 --window-days 29 --max-pages 1
python -m fraud_lens_gov backfill-compras-csv --start-year 2021 --end-year 2026 --limit-per-year 5000
python -m fraud_lens_gov build-silver --source compras_gov
python -m fraud_lens_gov build-golden --analyze --cluster --categorize
```

`build-golden` is incremental by default: it only materializes items that are new or stale compared with the Golden layer. Use `--full-refresh` when changing quality/comparability rules and intentionally rebuilding the whole analytic layer.

Golden does not treat every similar description as comparable. It blocks procurement-object rows, weak/generic descriptions without catalog metadata, broad service scopes, unknown units, and item families that need structured specs before price benchmarking (for example manipulated formulas, food-service bundles, and medical-device families).

Run long Bronze/Silver/Golden jobs in the background and track progress in the dashboard:

```powershell
python -m fraud_lens_gov backfill-bronze --source both --async
python -m fraud_lens_gov backfill-compras-csv --start-year 2021 --end-year 2026 --limit-per-year 5000 --async
python -m fraud_lens_gov build-silver --source compras_gov --limit 5000 --async
```

For historical item-level data, prefer the official Compras.gov.br CSV repository (`backfill-compras-csv`). The REST API remains useful for smaller recent windows, while annual CSV files are the safer path for large backfills.

Export an auditable alert package:

```powershell
python -m fraud_lens_gov export-alerts --format md --output reports/alerts.md --limit 25
```

## Local Investigation API

The dashboard also exposes JSON endpoints for audit workflows:

```text
GET /api/summary
GET /api/pipeline
GET /api/knn-review
GET /api/clusters/{cluster_id}
GET /api/alerts/{alert_id}
GET /api/items/{item_id}/neighbors
```

Cluster, alert, and comparison links are available directly in the dashboard. Alert detail pages under `/investigacao/alertas/{alert_id}` show the investigated item, normalized price, median of comparable neighbors, comparison rows, and a deterministic audit narrative.

Google Programmable Search for local portal discovery:

```powershell
$env:GOOGLE_API_KEY="..."
$env:GOOGLE_SEARCH_ENGINE_ID="..."
python -m fraud_lens_gov discover-portals "portal transparencia licitacoes prefeitura"
```

OpenAI alert explanations:

```powershell
$env:OPENAI_API_KEY="..."
python -m fraud_lens_gov explain-alerts --limit 10
```

Without `OPENAI_API_KEY`, the app keeps deterministic local explanations.

## RAG Direction

FraudLensGov is not meant to be tied to a single chat model. The intended AI layer is broader:

- RAG over edital, termo de referencia, contract attachments, and historical decisions.
- Semantic normalization of item categories, SKUs, CATMAT/CATSER, NCM, and free-text descriptions.
- Cluster explanation for groups of comparable items and suppliers.
- Auditable alert narratives that separate source facts, statistical inference, and hypotheses.

## Architecture

```text
PNCP / Compras.gov.br / Portais locais / Google discovery
        |
        v
Bronze Layer: payload bruto por fonte, janela e endpoint
        |
        v
Silver Layer: normalizacao SQL + enriquecimento publico de item
        |
        v
Golden Layer: dataset auditavel, metadados de qualidade e comparabilidade
        |
        v
Base historica de precos por item, regiao, orgao, fornecedor e data
        |
        v
Motor estatistico de anomalias, clusters e outliers
        |
        v
RAG + GenAI explicando o alerta e lendo edital/termo de referencia
        |
        v
Dashboard de risco + relatorio auditavel
```

Read the full implementation plan in [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md).

## Supply-Chain Posture

The runtime dependency surface is intentionally small. Django is the product web dependency, pinned exactly in `requirements.txt` along with its direct runtime dependencies. The ingestion, normalization, statistical analysis, clustering, export, and RAG prototype code remain standard-library Python.

Next hardening steps are a lockfile, package audit, Dependabot/GitHub security alerts, and avoiding packages for trivial utilities.

## Status

Early prototype.

## License

MIT. See [LICENSE](LICENSE).
