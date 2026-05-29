from __future__ import annotations

import html
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from .storage import Storage


def serve(storage: Storage, host: str = "127.0.0.1", port: int = 8080) -> None:
    class Handler(DashboardHandler):
        app_storage = storage

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"FraudLensGov dashboard running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()


class DashboardHandler(BaseHTTPRequestHandler):
    app_storage: Storage

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send_html(render_dashboard(self.app_storage.dashboard_summary()))
            return
        if path == "/api/summary":
            self._send_json(self.app_storage.dashboard_summary())
            return
        if path == "/api/pipeline":
            summary = self.app_storage.dashboard_summary()
            self._send_json({
                "layers": summary.get("layers", {}),
                "pipeline_jobs": summary.get("pipeline_jobs", []),
            })
            return
        if path.startswith("/api/clusters/"):
            cluster_id = unquote(path.removeprefix("/api/clusters/"))
            detail = self.app_storage.cluster_detail(cluster_id)
            if detail is None:
                self.send_error(HTTPStatus.NOT_FOUND, "Cluster not found")
                return
            self._send_json(detail)
            return
        if path.startswith("/api/items/") and path.endswith("/neighbors"):
            item_id = unquote(path.removeprefix("/api/items/").removesuffix("/neighbors"))
            self._send_json({"item_id": item_id, "neighbors": self.app_storage.item_neighbors(item_id)})
            return
        if path.startswith("/api/alerts/"):
            alert_id = unquote(path.removeprefix("/api/alerts/"))
            detail = self.app_storage.alert_detail(alert_id)
            if detail is None:
                self.send_error(HTTPStatus.NOT_FOUND, "Alert not found")
                return
            self._send_json(detail)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_html(self, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def render_dashboard(summary: dict[str, object]) -> str:
    totals = summary["totals"]
    alerts = summary["alerts"]
    risk_types = summary["risk_types"]
    top_alerts = summary["top_alerts"]
    cluster_totals = summary.get("cluster_totals", {"clusters": 0, "clustered_items": 0})
    top_clusters = summary.get("top_clusters", [])
    ingestion_runs = summary.get("ingestion_runs", [])
    layers = summary.get("layers", {})
    pipeline_jobs = summary.get("pipeline_jobs", [])
    posture = _risk_posture(alerts)
    risk_rows = "".join(_render_risk_type(row) for row in risk_types)
    alert_rows = "".join(_render_alert_row(row) for row in top_alerts)
    cluster_rows = "".join(_render_cluster(row) for row in top_clusters)
    run_rows = "".join(_render_ingestion_run(row) for row in ingestion_runs)
    layer_rows = _render_layers(layers)
    job_rows = "".join(_render_pipeline_job(row) for row in pipeline_jobs)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FraudLensGov</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f8f8f8;
      --surface: #ffffff;
      --surface-2: #f3f5f7;
      --ink: #1b1b1b;
      --muted: #555d66;
      --line: #dfe1e2;
      --line-strong: #c7c9cc;
      --blue: #1351b4;
      --blue-dark: #071d41;
      --blue-soft: #e8f1ff;
      --green: #168821;
      --yellow: #ffcd07;
      --orange: #b57900;
      --red: #e52207;
      --shadow: 0 12px 30px rgba(7, 29, 65, .08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        linear-gradient(180deg, #ffffff 0, #f3f5f7 250px, #f8f8f8 100%);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }}
    .topbar {{
      background: #ffffff;
      color: var(--blue-dark);
      border-bottom: 1px solid var(--line);
      box-shadow: 0 2px 12px rgba(7, 29, 65, .06);
    }}
    .topbar-inner {{
      max-width: 1320px;
      margin: 0 auto;
      padding: 18px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 14px;
      min-width: 0;
    }}
    .seal {{
      width: 46px;
      height: 46px;
      border: 2px solid var(--blue);
      display: grid;
      place-items: center;
      font-weight: 800;
      background: linear-gradient(135deg, #ffffff 0, var(--blue-soft) 100%);
      color: var(--blue);
      flex: 0 0 auto;
    }}
    h1 {{
      margin: 0;
      font-size: 22px;
      line-height: 1.1;
      letter-spacing: 0;
    }}
    .kicker {{
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 13px;
    }}
    .status-strip {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    .status-chip {{
      border: 1px solid #c5d4eb;
      background: var(--blue-soft);
      color: var(--blue);
      padding: 7px 10px;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }}
    main {{
      max-width: 1320px;
      margin: 0 auto;
      padding: 28px 24px 46px;
    }}
    .command-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.6fr) minmax(300px, .8fr);
      gap: 18px;
      align-items: stretch;
    }}
    .hero-panel {{
      background: var(--surface);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      padding: 24px;
      border-top: 4px solid var(--blue);
    }}
    .hero-eyebrow {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 18px;
    }}
    .section-label {{
      color: var(--blue);
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: .08em;
    }}
    .risk-badge {{
      background: {posture["color"]};
      color: #fff;
      padding: 8px 12px;
      font-size: 13px;
      font-weight: 800;
      text-transform: uppercase;
    }}
    .hero-title {{
      margin: 0;
      font-size: clamp(30px, 4vw, 52px);
      line-height: 1;
      max-width: 850px;
      letter-spacing: 0;
      color: var(--blue-dark);
    }}
    .hero-copy {{
      max-width: 850px;
      margin: 14px 0 0;
      color: var(--muted);
      font-size: 16px;
      line-height: 1.55;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 12px;
      margin-top: 22px;
    }}
    .metric {{
      border-top: 3px solid var(--blue);
      background: var(--surface-2);
      padding: 15px;
      min-height: 102px;
    }}
    .metric span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
      margin-bottom: 9px;
    }}
    .metric strong {{
      display: block;
      font-size: 26px;
      line-height: 1.1;
      letter-spacing: 0;
    }}
    .side-panel {{
      background: #ffffff;
      color: var(--blue-dark);
      border: 1px solid var(--line);
      border-top: 4px solid var(--yellow);
      box-shadow: var(--shadow);
      padding: 22px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      min-height: 100%;
    }}
    .side-panel h2 {{
      margin: 0 0 14px;
      font-size: 19px;
      letter-spacing: 0;
    }}
    .chain {{
      display: grid;
      gap: 12px;
      margin-top: 18px;
    }}
    .chain-row {{
      display: grid;
      grid-template-columns: 34px 1fr;
      gap: 11px;
      align-items: start;
    }}
    .chain-mark {{
      height: 34px;
      display: grid;
      place-items: center;
      border: 1px solid #c5d4eb;
      color: var(--blue);
      font-weight: 800;
      background: var(--blue-soft);
    }}
    .chain-row strong {{
      display: block;
      font-size: 14px;
    }}
    .chain-row span {{
      display: block;
      margin-top: 3px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.35;
    }}
    .content-grid {{
      display: grid;
      grid-template-columns: minmax(280px, .45fr) minmax(0, 1fr);
      gap: 18px;
      margin-top: 18px;
    }}
    .section-wide {{
      grid-column: 1 / -1;
    }}
    section {{
      background: var(--surface);
      border: 1px solid var(--line);
      box-shadow: 0 12px 28px rgba(17, 24, 39, .06);
      min-width: 0;
    }}
    .section-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
      background: #f8fafc;
    }}
    .section-head h2 {{
      margin: 0;
      font-size: 16px;
      letter-spacing: 0;
    }}
    .small-note {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }}
    .risk-list {{
      padding: 12px;
      display: grid;
      gap: 10px;
    }}
    .pipeline-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(300px, .9fr);
      gap: 12px;
      padding: 12px;
    }}
    .layer-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }}
    .layer-item,
    .job-item {{
      border: 1px solid var(--line);
      background: #fff;
      padding: 12px;
      min-width: 0;
    }}
    .layer-item {{
      border-top: 4px solid var(--blue);
      min-height: 116px;
    }}
    .layer-item strong {{
      display: block;
      color: var(--blue-dark);
      font-size: 14px;
      text-transform: uppercase;
    }}
    .layer-item b {{
      display: block;
      margin: 8px 0;
      font-size: 26px;
      line-height: 1;
    }}
    .layer-item span,
    .job-item span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }}
    .job-list {{
      display: grid;
      gap: 10px;
    }}
    .job-head {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: start;
      margin-bottom: 9px;
    }}
    .job-title {{
      color: var(--blue-dark);
      font-weight: 900;
      font-size: 13px;
      text-transform: uppercase;
    }}
    .progress-track {{
      height: 8px;
      background: var(--surface-2);
      border: 1px solid var(--line);
      overflow: hidden;
      margin: 8px 0;
    }}
    .progress-fill {{
      height: 100%;
      background: var(--blue);
    }}
    .risk-item {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: center;
      padding: 12px;
      border-left: 4px solid var(--yellow);
      background: #fffdf2;
    }}
    .risk-item strong {{
      display: block;
      font-size: 13px;
    }}
    .risk-item span {{
      color: var(--muted);
      font-size: 12px;
    }}
    .risk-count {{
      font-size: 22px;
      font-weight: 900;
      color: var(--blue);
    }}
    .cluster-list,
    .run-list {{
      padding: 12px;
      display: grid;
      gap: 10px;
    }}
    .cluster-item,
    .run-item {{
      padding: 12px;
      border: 1px solid var(--line);
      background: #fff;
    }}
    .cluster-item {{
      border-left: 4px solid var(--blue);
    }}
    .run-item {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: start;
      border-left: 4px solid var(--green);
    }}
    .cluster-title,
    .run-title {{
      display: block;
      color: var(--blue-dark);
      font-size: 13px;
      font-weight: 900;
      text-transform: uppercase;
    }}
    .action-link {{
      color: var(--blue);
      text-decoration: none;
    }}
    .action-link:hover {{
      text-decoration: underline;
    }}
    .cluster-meta,
    .run-meta {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
      margin-top: 4px;
    }}
    .status-ok,
    .status-running,
    .status-failed,
    .status-partial {{
      display: inline-block;
      padding: 4px 7px;
      color: #fff;
      font-size: 11px;
      font-weight: 800;
      text-transform: uppercase;
    }}
    .status-ok {{ background: var(--green); }}
    .status-running {{ background: var(--blue); }}
    .status-failed {{ background: var(--red); }}
    .status-partial {{ background: var(--orange); }}
    .table-wrap {{
      display: block;
      overflow-x: auto;
      max-width: 100%;
    }}
    table {{
      width: 100%;
      min-width: 980px;
      border-collapse: collapse;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 13px 14px;
      text-align: left;
      vertical-align: top;
      font-size: 14px;
    }}
    th {{
      background: #f0f4fa;
      color: var(--blue-dark);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .06em;
      position: sticky;
      top: 0;
      z-index: 1;
    }}
    tr:hover td {{
      background: #f7faff;
    }}
    .severity {{
      display: inline-grid;
      place-items: center;
      min-width: 34px;
      height: 30px;
      color: #fff;
      background: #b57900;
      font-weight: 900;
    }}
    .severity.high {{
      background: var(--red);
    }}
    .alert-title {{
      display: block;
      max-width: 360px;
      font-weight: 800;
      color: var(--ink);
    }}
    .muted {{
      color: var(--muted);
      line-height: 1.45;
    }}
    .money {{
      white-space: nowrap;
      font-weight: 800;
    }}
    .empty {{
      padding: 20px;
      color: var(--muted);
    }}
    @media (max-width: 980px) {{
      .command-grid,
      .content-grid,
      .pipeline-grid {{
        grid-template-columns: 1fr;
      }}
      .metrics {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .layer-grid {{
        grid-template-columns: 1fr;
      }}
      .topbar-inner {{
        align-items: flex-start;
        flex-direction: column;
      }}
      .status-strip {{
        justify-content: flex-start;
      }}
    }}
    @media (max-width: 560px) {{
      main {{
        padding: 18px 14px 32px;
      }}
      .topbar-inner {{
        padding: 16px 14px;
      }}
      .hero-panel,
      .side-panel {{
        padding: 18px;
      }}
      .metrics {{
        grid-template-columns: 1fr;
      }}
      .hero-eyebrow {{
        align-items: flex-start;
        flex-direction: column;
      }}
    }}
  </style>
</head>
<body>
  <header class="topbar">
    <div class="topbar-inner">
      <div class="brand">
        <div class="seal">FG</div>
        <div>
          <h1>FraudLensGov</h1>
          <p class="kicker">Sala de auditoria publica para contratacoes, precos e fornecedores</p>
        </div>
      </div>
      <div class="status-strip">
        <span class="status-chip">Fonte publica</span>
        <span class="status-chip">Evidencia rastreavel</span>
        <span class="status-chip">Revisao humana</span>
      </div>
    </div>
  </header>
  <main>
    <div class="command-grid">
      <section class="hero-panel">
        <div class="hero-eyebrow">
          <span class="section-label">Painel de comando</span>
          <span class="risk-badge">{posture["label"]}</span>
        </div>
        <h2 class="hero-title">Risco publico sob revisao, com trilha de evidencia.</h2>
        <p class="hero-copy">A fila abaixo consolida compras, fornecedores, valores unitarios e sinais estatisticos para orientar auditoria, controle social e revisao documental.</p>
        <div class="metrics">
          <div class="metric"><span>Itens analisados</span><strong>{totals["items"]}</strong></div>
          <div class="metric"><span>Valor observado</span><strong>{compact_money(totals["total_value"])}</strong></div>
          <div class="metric"><span>Fornecedores</span><strong>{totals["suppliers"]}</strong></div>
          <div class="metric"><span>Clusters</span><strong>{cluster_totals["clusters"]}</strong></div>
          <div class="metric"><span>Alertas ativos</span><strong>{alerts["alerts"]}</strong></div>
        </div>
      </section>
      <aside class="side-panel">
        <div>
          <span class="section-label">Cadeia de custodia</span>
          <h2>Da fonte publica ao parecer auditavel</h2>
          <div class="chain">
            <div class="chain-row"><div class="chain-mark">1</div><div><strong>Ingestao</strong><span>PNCP, Compras.gov.br e portais locais preservando payload bruto.</span></div></div>
            <div class="chain-row"><div class="chain-mark">2</div><div><strong>Normalizacao</strong><span>Itens, orgaos, fornecedores, datas, regioes e valores comparaveis.</span></div></div>
            <div class="chain-row"><div class="chain-mark">3</div><div><strong>Analise</strong><span>Outliers, concentracao, fracionamento e vizinhos de preco.</span></div></div>
            <div class="chain-row"><div class="chain-mark">4</div><div><strong>Relatorio</strong><span>Explicacao com evidencia, incerteza e proximas verificacoes.</span></div></div>
          </div>
        </div>
      </aside>
    </div>

    <div class="content-grid">
      <section class="section-wide">
        <div class="section-head">
          <h2>Pipeline de dados</h2>
          <span class="small-note">Bronze / Silver / Golden</span>
        </div>
        <div class="pipeline-grid">
          <div class="layer-grid">{layer_rows}</div>
          <div class="job-list">{job_rows or '<div class="empty">Nenhum processamento em andamento.</div>'}</div>
        </div>
      </section>

      <section>
        <div class="section-head">
          <h2>Mapa de risco</h2>
          <span class="small-note">Por tipologia</span>
        </div>
        <div class="risk-list">
          {risk_rows or '<div class="empty">Nenhum alerta gerado.</div>'}
        </div>
      </section>

      <section>
        <div class="section-head">
          <h2>Clusters comparaveis</h2>
          <span class="small-note">KNN lexical</span>
        </div>
        <div class="cluster-list">
          {cluster_rows or '<div class="empty">Execute build-clusters para materializar agrupamentos.</div>'}
        </div>
      </section>

      <section>
        <div class="section-head">
          <h2>Ultimas ingestoes</h2>
          <span class="small-note">Trilha operacional</span>
        </div>
        <div class="run-list">
          {run_rows or '<div class="empty">Nenhuma ingestao registrada.</div>'}
        </div>
      </section>

      <section class="section-wide">
        <div class="section-head">
          <h2>Fila de revisao</h2>
          <span class="small-note">Prioridade por severidade</span>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Sev.</th><th>Score</th><th>Alerta</th><th>Item</th><th>Orgao</th>
                <th>Fornecedor</th><th>Valor</th><th>Data</th>
              </tr>
            </thead>
            <tbody>{alert_rows or '<tr><td colspan="8" class="empty">Execute a analise para preencher a fila.</td></tr>'}</tbody>
          </table>
        </div>
      </section>
    </div>
  </main>
</body>
</html>"""


def _risk_posture(alerts: dict[str, object]) -> dict[str, str]:
    max_severity = int(alerts.get("max_severity") or 0)
    alert_count = int(alerts.get("alerts") or 0)
    if max_severity >= 3:
        return {"label": "Risco critico", "color": "var(--red)"}
    if alert_count:
        return {"label": "Risco elevado", "color": "var(--orange)"}
    return {"label": "Sem alerta ativo", "color": "var(--green)"}


def _render_risk_type(row: dict[str, object]) -> str:
    label = str(row["risk_type"]).replace("_", " ").title()
    count = int(row["count"])
    return f"""
      <div class="risk-item">
        <div><strong>{escape(label)}</strong><span>Alertas aguardando revisao</span></div>
        <div class="risk-count">{count}</div>
      </div>"""


def _render_layers(layers: object) -> str:
    data = layers if isinstance(layers, dict) else {}
    bronze = data.get("bronze", {}) if isinstance(data.get("bronze", {}), dict) else {}
    silver = data.get("silver", {}) if isinstance(data.get("silver", {}), dict) else {}
    golden = data.get("golden", {}) if isinstance(data.get("golden", {}), dict) else {}
    rows = [
        ("Bronze", bronze.get("total", 0), f"pendentes {bronze.get('pending', 0)} | silver {bronze.get('silvered', 0)} | falhas {bronze.get('failed', 0)}"),
        ("Silver", silver.get("total", 0), "itens normalizados em tabela operacional"),
        ("Golden", golden.get("total", 0), f"comparaveis {golden.get('comparable', 0)} | genericos {golden.get('generic', 0)} | ausentes {golden.get('missing', 0)}"),
    ]
    return "".join(
        f"""
        <div class="layer-item">
          <strong>{escape(label)}</strong>
          <b>{int(value or 0)}</b>
          <span>{escape(meta)}</span>
        </div>"""
        for label, value, meta in rows
    )


def _render_pipeline_job(row: dict[str, object]) -> str:
    status = str(row.get("status") or "").lower()
    status_class = {
        "success": "status-ok",
        "running": "status-running",
        "failed": "status-failed",
        "partial": "status-partial",
    }.get(status, "status-running")
    progress = max(0.0, min(float(row.get("progress") or 0), 100.0))
    return f"""
      <div class="job-item">
        <div class="job-head">
          <div>
            <div class="job-title">{escape(row.get("name"))}</div>
            <span>{escape(row.get("layer"))} | {escape(row.get("current_step") or "aguardando")}</span>
          </div>
          <span class="{status_class}">{escape(status or "n/a")}</span>
        </div>
        <div class="progress-track"><div class="progress-fill" style="width: {progress:.2f}%"></div></div>
        <span>{progress:.0f}% | {int(row.get("steps_done") or 0)} de {int(row.get("steps_total") or 0)} etapas | {escape(row.get("message"))}</span>
      </div>"""


def _render_cluster(row: dict[str, object]) -> str:
    states = _states(row.get("states"))
    label = str(row.get("label") or "Cluster sem rotulo")
    return f"""
      <div class="cluster-item">
        <a class="cluster-title action-link" href="/api/clusters/{escape(row.get('id'))}">{escape(label)}</a>
        <span class="cluster-meta">
          {int(row.get("item_count") or 0)} itens | media {money(row.get("avg_unit_price"))}
          | faixa {money(row.get("min_unit_price"))} - {money(row.get("max_unit_price"))}
          | UF {escape(", ".join(states) or "N/A")}
        </span>
      </div>"""


def _render_ingestion_run(row: dict[str, object]) -> str:
    status = str(row.get("status") or "").lower()
    status_class = {
        "success": "status-ok",
        "running": "status-running",
        "failed": "status-failed",
    }.get(status, "status-running")
    return f"""
      <div class="run-item">
        <div>
          <span class="run-title">{escape(row.get("source"))}</span>
          <span class="run-meta">
            {int(row.get("records_written") or 0)} gravados de {int(row.get("records_read") or 0)} lidos
            | inicio {escape(row.get("started_at"))}
          </span>
        </div>
        <span class="{status_class}">{escape(status or "n/a")}</span>
      </div>"""


def _render_alert_row(row: dict[str, object]) -> str:
    severity = int(row["severity"])
    sev_class = "severity high" if severity >= 3 else "severity"
    explanation = row.get("genai_explanation") or row.get("explanation") or ""
    quality = row.get("description_quality") or {}
    quality_label = str(quality.get("level") or "unknown")
    return f"""
    <tr>
      <td><span class="{sev_class}">{severity}</span></td>
      <td>{float(row['score']):.2f}</td>
      <td><a class="alert-title action-link" href="/api/alerts/{escape(row['id'])}">{escape(row['title'])}</a><span class="muted">{escape(explanation)}</span></td>
      <td>{escape(row['item_description'])}<br><span class="muted">{escape(row['state'])} | qualidade: {escape(quality_label)}</span></td>
      <td>{escape(row['agency_name'])}</td>
      <td>{escape(row['supplier_name'] or 'Nao informado')}<br><a class="action-link muted" href="/api/items/{escape(row['item_id'])}/neighbors">vizinhos</a></td>
      <td class="money">{money(row['total_value'])}</td>
      <td>{escape(row['procurement_date'])}</td>
    </tr>"""


def money(value: object) -> str:
    amount = float(value or 0)
    return f"R$ {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def compact_money(value: object) -> str:
    amount = float(value or 0)
    if abs(amount) >= 1_000_000_000:
        return f"R$ {amount / 1_000_000_000:.1f} bi".replace(".", ",")
    if abs(amount) >= 1_000_000:
        return f"R$ {amount / 1_000_000:.1f} mi".replace(".", ",")
    if abs(amount) >= 1_000:
        return f"R$ {amount / 1_000:.1f} mil".replace(".", ",")
    return money(amount)


def _states(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value] if value else []
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []


def escape(value: object) -> str:
    return html.escape("" if value is None else str(value))
