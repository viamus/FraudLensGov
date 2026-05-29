from __future__ import annotations

import html
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

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
    risk_rows = "".join(
        f"<tr><td>{escape(row['risk_type'])}</td><td>{row['count']}</td></tr>" for row in risk_types
    )
    alert_rows = "".join(_render_alert_row(row) for row in top_alerts)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FraudLensGov</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fa;
      --panel: #ffffff;
      --ink: #18202a;
      --muted: #667085;
      --line: #d7dde5;
      --accent: #0b766e;
      --warn: #b54708;
      --danger: #b42318;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }}
    header {{
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      padding: 22px 28px;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 26px 22px 42px;
    }}
    h1 {{
      margin: 0;
      font-size: 24px;
      letter-spacing: 0;
    }}
    .subtitle {{
      margin: 8px 0 0;
      color: var(--muted);
      max-width: 900px;
      line-height: 1.5;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin-bottom: 24px;
    }}
    .metric {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .metric span {{
      display: block;
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 8px;
    }}
    .metric strong {{
      font-size: 25px;
      letter-spacing: 0;
    }}
    section {{
      margin-top: 24px;
    }}
    h2 {{
      font-size: 17px;
      margin: 0 0 12px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 11px 12px;
      text-align: left;
      vertical-align: top;
      font-size: 14px;
    }}
    th {{
      background: #edf1f5;
      color: #344054;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }}
    tr:last-child td {{ border-bottom: 0; }}
    .severity {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 34px;
      height: 26px;
      border-radius: 999px;
      color: #fff;
      background: var(--warn);
      font-weight: 700;
    }}
    .severity.high {{ background: var(--danger); }}
    .muted {{ color: var(--muted); }}
    .money {{ white-space: nowrap; }}
    @media (max-width: 800px) {{
      .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      table {{ display: block; overflow-x: auto; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>FraudLensGov</h1>
    <p class="subtitle">Triagem local de riscos em compras publicas: ingestao, normalizacao, sinais estatisticos, clusters e relatorios explicaveis para revisao humana.</p>
  </header>
  <main>
    <div class="metrics">
      <div class="metric"><span>Itens analisados</span><strong>{totals['items']}</strong></div>
      <div class="metric"><span>Valor observado</span><strong>{money(totals['total_value'])}</strong></div>
      <div class="metric"><span>Fornecedores</span><strong>{totals['suppliers']}</strong></div>
      <div class="metric"><span>Alertas</span><strong>{alerts['alerts']}</strong></div>
    </div>
    <section>
      <h2>Alertas por tipo</h2>
      <table>
        <thead><tr><th>Tipo</th><th>Quantidade</th></tr></thead>
        <tbody>{risk_rows or '<tr><td colspan="2" class="muted">Nenhum alerta gerado.</td></tr>'}</tbody>
      </table>
    </section>
    <section>
      <h2>Fila de revisao</h2>
      <table>
        <thead>
          <tr>
            <th>Sev.</th><th>Score</th><th>Alerta</th><th>Item</th><th>Orgao</th>
            <th>Fornecedor</th><th>Valor</th><th>Data</th>
          </tr>
        </thead>
        <tbody>{alert_rows or '<tr><td colspan="8" class="muted">Execute a analise para preencher a fila.</td></tr>'}</tbody>
      </table>
    </section>
  </main>
</body>
</html>"""


def _render_alert_row(row: dict[str, object]) -> str:
    severity = int(row["severity"])
    sev_class = "severity high" if severity >= 3 else "severity"
    explanation = row.get("genai_explanation") or row.get("explanation") or ""
    return f"""
    <tr>
      <td><span class="{sev_class}">{severity}</span></td>
      <td>{float(row['score']):.2f}</td>
      <td><strong>{escape(row['title'])}</strong><br><span class="muted">{escape(explanation)}</span></td>
      <td>{escape(row['item_description'])}<br><span class="muted">{escape(row['state'])}</span></td>
      <td>{escape(row['agency_name'])}</td>
      <td>{escape(row['supplier_name'] or 'Nao informado')}</td>
      <td class="money">{money(row['total_value'])}</td>
      <td>{escape(row['procurement_date'])}</td>
    </tr>"""


def money(value: object) -> str:
    amount = float(value or 0)
    return f"R$ {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def escape(value: object) -> str:
    return html.escape("" if value is None else str(value))
