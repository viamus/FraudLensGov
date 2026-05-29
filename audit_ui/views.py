from __future__ import annotations

import csv
import json
from math import ceil
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render

from fraud_lens_gov.storage import Storage
from fraud_lens_gov.unit_normalization import adjusted_price_for_unit


def dashboard(request):
    return _render_dashboard(request, "overview")


def pipeline_page(request):
    return _render_dashboard(request, "pipeline")


def quality_page(request):
    return _render_dashboard(request, "qualidade")


def investigation_page(request):
    return _render_dashboard(request, "investigacao")


def neighbors_page(request):
    return _render_dashboard(request, "vizinhos")


def alert_detail_page(request, alert_id: str):
    storage = _storage()
    detail = storage.alert_detail(alert_id)
    if detail is None:
        raise Http404("Alert not found")
    summary = storage.dashboard_summary()
    return render(request, "audit_ui/alert_detail.html", _alert_detail_context(summary, detail))


def normalization_page(request):
    return _render_dashboard(request, "normalizacao")


def clusters_page(request):
    return _render_dashboard(request, "clusters")


def operation_page(request):
    return _render_dashboard(request, "operacao")


def ingestion_page(request):
    return _render_dashboard(request, "ingestoes")


def _render_dashboard(request, active_page: str):
    storage = _storage()
    summary = storage.dashboard_summary()
    return render(request, "audit_ui/dashboard.html", _dashboard_context(summary, active_page, request.GET, storage))


def summary_api(request):
    return _json(_storage().dashboard_summary())


def pipeline_api(request):
    summary = _storage().dashboard_summary()
    return _json(
        {
            "layers": summary.get("layers", {}),
            "pipeline_jobs": summary.get("pipeline_jobs", []),
        }
    )


def knn_review_api(request):
    storage = _storage()
    return _json(
        {
            "pairs": storage.knn_review_queue(limit=50),
            "blocked": storage.knn_blocked_items(limit=50),
        }
    )


def cluster_detail_api(request, cluster_id: str):
    detail = _storage().cluster_detail(cluster_id)
    if detail is None:
        raise Http404("Cluster not found")
    return _json(detail)


def alert_detail_api(request, alert_id: str):
    detail = _storage().alert_detail(alert_id)
    if detail is None:
        raise Http404("Alert not found")
    return _json(detail)


def item_neighbors_api(request, item_id: str):
    return _json({"item_id": item_id, "neighbors": _storage().item_neighbors(item_id)})


def table_export_csv(request, table_key: str):
    storage = _storage()
    query = request.GET
    table = _export_table(storage, query, table_key)
    if table is None:
        raise Http404("Export table not found")

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="fraudlens-{table_key}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    columns = table["columns"]
    writer.writerow([column["label"] for column in columns])
    for row in table["rows"]:
        writer.writerow([_csv_value(row.get(column["key"])) for column in columns])
    return response


def _storage() -> Storage:
    storage = Storage(Path(settings.FRAUDLENS_DB))
    storage.init_schema()
    return storage


def _json(payload: dict[str, Any]) -> JsonResponse:
    return JsonResponse(payload, json_dumps_params={"ensure_ascii": False, "indent": 2})


def _export_table(storage: Storage, query: Any, table_key: str) -> dict[str, Any] | None:
    columns_by_table = {
        "alerts": [
            {"key": "severity", "label": "Severidade"},
            {"key": "risk_label", "label": "Risco"},
            {"key": "item_description", "label": "Item"},
            {"key": "agency_name", "label": "Orgao"},
            {"key": "supplier_name", "label": "Fornecedor"},
            {"key": "state", "label": "UF"},
            {"key": "total_value", "label": "Valor total"},
            {"key": "score", "label": "Score"},
            {"key": "quality_level", "label": "Qualidade"},
            {"key": "detail_href", "label": "Detalhe"},
        ],
        "jobs": [
            {"key": "name", "label": "Job"},
            {"key": "layer", "label": "Camada"},
            {"key": "current_step", "label": "Etapa"},
            {"key": "status", "label": "Status"},
            {"key": "progress", "label": "Progresso"},
            {"key": "message", "label": "Mensagem"},
            {"key": "started_at", "label": "Inicio"},
            {"key": "updated_at", "label": "Atualizacao"},
        ],
        "runs": [
            {"key": "source", "label": "Fonte"},
            {"key": "status", "label": "Status"},
            {"key": "records_read", "label": "Lidos"},
            {"key": "records_written", "label": "Gravados"},
            {"key": "parameters_display", "label": "Parametros"},
            {"key": "started_at", "label": "Inicio"},
            {"key": "finished_at", "label": "Fim"},
            {"key": "error", "label": "Erro"},
        ],
        "categories": [
            {"key": "category", "label": "Categoria"},
            {"key": "item_count", "label": "Itens"},
            {"key": "avg_confidence", "label": "Confianca media"},
            {"key": "needs_rag", "label": "Pedem RAG"},
        ],
        "clusters": [
            {"key": "label", "label": "Cluster"},
            {"key": "item_count", "label": "Itens"},
            {"key": "avg_unit_price", "label": "Media"},
            {"key": "min_unit_price", "label": "Minimo"},
            {"key": "max_unit_price", "label": "Maximo"},
            {"key": "total_value", "label": "Valor total"},
            {"key": "states_display", "label": "UFs"},
        ],
        "knn": [
            {"key": "item_description", "label": "Item"},
            {"key": "neighbor_description", "label": "Vizinho"},
            {"key": "unit", "label": "Unidade"},
            {"key": "neighbor_unit", "label": "Unidade vizinho"},
            {"key": "adjusted_unit_price", "label": "Preco normalizado"},
            {"key": "neighbor_adjusted_unit_price", "label": "Preco normalizado vizinho"},
            {"key": "price_ratio", "label": "Diferenca"},
            {"key": "similarity", "label": "Similaridade"},
        ],
    }
    builders = {
        "alerts": _alert_table,
        "jobs": _job_table,
        "runs": _run_table,
        "categories": _category_table,
        "clusters": _cluster_table,
        "knn": _knn_table,
    }
    builder = builders.get(table_key)
    columns = columns_by_table.get(table_key)
    if builder is None or columns is None:
        return None
    export_query = {key: value for key, value in _query_params(query).items() if not key.endswith("_page")}
    table = builder(storage, export_query, page_size=10000)
    return {"rows": table["rows"], "columns": columns}


def _dashboard_context(
    summary: dict[str, Any],
    active_page: str,
    query: Any,
    storage: Storage,
) -> dict[str, Any]:
    totals = _dict(summary.get("totals"))
    alerts = _dict(summary.get("alerts"))
    category_totals = _dict(summary.get("category_totals"))
    cluster_totals = _dict(summary.get("cluster_totals"))
    layers = _dict(summary.get("layers"))
    golden = _dict(layers.get("golden"))
    bronze = _dict(layers.get("bronze"))
    silver = _dict(layers.get("silver"))
    knn_review = _dict(summary.get("knn_review"))
    pairs = _as_list(knn_review.get("pairs"))
    blocked = _as_list(knn_review.get("blocked"))
    alert_table = _alert_table(storage, query, page_size=5 if active_page == "overview" else 12)
    job_table = _job_table(storage, query, page_size=3 if active_page == "overview" else 8)
    run_table = _run_table(storage, query, page_size=8)
    category_table = _category_table(storage, query, page_size=8)
    cluster_table = _cluster_table(storage, query, page_size=8)
    knn_table = _knn_table(storage, query, page_size=8)
    jobs = job_table["rows"]
    clusters = cluster_table["rows"]
    categories = category_table["rows"]
    risk_types = [_risk_type_view(row) for row in _as_list(summary.get("risk_types"))]
    top_alerts = alert_table["rows"]
    ingestion_runs = run_table["rows"]
    knn_pairs = knn_table["rows"]
    comparable = _int(golden.get("comparable"))
    blocked_total = (
        _int(golden.get("missing"))
        + _int(golden.get("generic"))
        + _int(golden.get("weak"))
        + _int(golden.get("broad_scope"))
        + _int(golden.get("spec_required"))
        + _int(golden.get("unit_unknown"))
    )
    scope_total = _int(golden.get("procurement_scope"))

    page_copy = _page_copy(active_page)
    guidance = _page_guidance(
        active_page,
        alerts=_int(alerts.get("alerts")),
        pairs=_int(knn_table["page"]["total"]),
        categories=_int(category_table["page"]["total"]),
        clusters=_int(cluster_table["page"]["total"]),
        jobs=_int(job_table["page"]["total"]),
        runs=_int(run_table["page"]["total"]),
        comparable=comparable,
        blocked=blocked_total + scope_total,
        silver_total=_int(silver.get("total")),
    )
    return {
        "active_page": active_page,
        "page_title": page_copy["title"],
        "page_subtitle": page_copy["subtitle"],
        "guidance": guidance,
        "current_path": _page_path(active_page),
        "nav_items": _nav_items(active_page),
        "posture": _risk_posture(alerts),
        "metrics": [
            {"label": "Silver total", "value": _int(silver.get("total")), "note": "registros normalizados"},
            {"label": "Comparáveis", "value": comparable, "note": "aptos para benchmark"},
            {"label": "Fora do KNN", "value": blocked_total + scope_total, "note": f"{scope_total} objetos PNCP"},
            {"label": "Pares KNN", "value": _int(knn_table["page"]["total"]), "note": f"{_int(cluster_totals.get('neighbor_edges'))} arestas"},
            {"label": "Alertas", "value": _int(alerts.get("alerts")), "note": "estatísticos ativos"},
            {"label": "Valor bruto", "value": _compact_money(totals.get("total_value")), "note": "inclui escopos PNCP"},
        ],
        "layers": [
            {
                "name": "Bronze",
                "value": _int(bronze.get("total")),
                "meta": f"pendentes {_int(bronze.get('pending'))} | silver {_int(bronze.get('silvered'))}",
            },
            {
                "name": "Silver",
                "value": _int(silver.get("total")),
                "meta": "normalização operacional",
            },
            {
                "name": "Golden",
                "value": _int(golden.get("total")),
                "meta": f"{comparable} comparáveis | {blocked_total} bloqueados",
            },
        ],
        "quality": _quality_rows(golden, scope_total),
        "category_totals": {
            "categorized": _int(category_totals.get("categorized")),
            "confident": _int(category_totals.get("confident")),
            "needs_rag": _int(category_totals.get("needs_rag")),
        },
        "categories": categories,
        "alert_table": alert_table,
        "job_table": job_table,
        "run_table": run_table,
        "category_table": category_table,
        "cluster_table": cluster_table,
        "knn_table": knn_table,
        "knn_pairs": knn_pairs,
        "visible_alerts": top_alerts,
        "visible_jobs": jobs,
        "visible_knn_pairs": knn_pairs,
        "blocked_items": [_blocked_view(row) for row in blocked],
        "jobs": jobs,
        "clusters": clusters,
        "risk_types": risk_types,
        "top_alerts": top_alerts,
        "ingestion_runs": ingestion_runs,
        "db_path": str(settings.FRAUDLENS_DB),
    }


def _alert_detail_context(summary: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    alerts = _dict(summary.get("alerts"))
    evidence = _dict(detail.get("evidence"))
    quality = _dict(detail.get("description_quality"))
    adjusted = _float(evidence.get("adjusted_unit_price"))
    median = _float(evidence.get("neighbor_median"))
    ratio = _float(evidence.get("ratio"))
    comparison_rows = _comparison_rows(evidence, adjusted)
    return {
        "active_page": "investigacao",
        "page_title": "Detalhe do alerta",
        "page_subtitle": "Comparação de preço, vizinhos usados e narrativa auditável.",
        "nav_items": _nav_items("investigacao"),
        "posture": _risk_posture(alerts),
        "alert": {
            **detail,
            "display_title": _display_item(detail.get("item_description")),
            "risk_label": _risk_label(detail.get("risk_type")),
            "score_display": f"{_float(detail.get('score')):.2f}",
            "total_value_display": _money(detail.get("total_value")),
            "unit_price_display": _money(detail.get("unit_price")),
            "adjusted_unit_price_display": _money(adjusted),
            "neighbor_median_display": _money(median),
            "ratio_display": f"{ratio:.1f}x" if ratio else "N/A",
            "quality_level": quality.get("level", "unknown"),
            "quality_reason": quality.get("reason", ""),
            "comparison_count": _int(evidence.get("comparison_count")),
        },
        "comparison_rows": comparison_rows,
        "report_lines": _report_lines(detail, evidence, comparison_rows),
        "db_path": str(settings.FRAUDLENS_DB),
    }


def _alert_table(storage: Storage, query: Any, page_size: int) -> dict[str, Any]:
    prefix = "alerts"
    page = _query_page(query, prefix)
    sort = _sort_state(query, prefix, "severity", "desc")
    filters = {
        "q": _query_value(query, f"{prefix}_q"),
        "risk_type": _query_value(query, f"{prefix}_risk_type"),
        "severity": _query_value(query, f"{prefix}_severity"),
        "sort": sort["key"],
        "direction": sort["direction"],
    }
    result, page, total = _clamped_paginated_result(storage.paginated_alert_rows, page, page_size, filters)
    return {
        "rows": [_alert_view(row) for row in _as_list(result.get("rows"))],
        "filters": filters,
        "sort": sort,
        "sort_links": _sort_links(query, prefix, sort, ["severity", "risk", "total_value", "score", "quality"]),
        "export_url": _export_url(query, "alerts"),
        "page": _page_meta(query, prefix, page, page_size, total),
    }


def _job_table(storage: Storage, query: Any, page_size: int) -> dict[str, Any]:
    prefix = "jobs"
    page = _query_page(query, prefix)
    sort = _sort_state(query, prefix, "started_at", "desc")
    filters = {
        "q": _query_value(query, f"{prefix}_q"),
        "status": _query_value(query, f"{prefix}_status"),
        "layer": _query_value(query, f"{prefix}_layer"),
        "sort": sort["key"],
        "direction": sort["direction"],
    }
    result, page, total = _clamped_paginated_result(storage.paginated_pipeline_jobs, page, page_size, filters)
    return {
        "rows": [_job_view(row) for row in _as_list(result.get("rows"))],
        "filters": filters,
        "sort": sort,
        "sort_links": _sort_links(query, prefix, sort, ["name", "layer", "status", "progress", "message"]),
        "export_url": _export_url(query, "jobs"),
        "page": _page_meta(query, prefix, page, page_size, total),
    }


def _run_table(storage: Storage, query: Any, page_size: int) -> dict[str, Any]:
    prefix = "runs"
    page = _query_page(query, prefix)
    sort = _sort_state(query, prefix, "started_at", "desc")
    filters = {
        "q": _query_value(query, f"{prefix}_q"),
        "status": _query_value(query, f"{prefix}_status"),
        "source": _query_value(query, f"{prefix}_source"),
        "sort": sort["key"],
        "direction": sort["direction"],
    }
    result, page, total = _clamped_paginated_result(storage.paginated_ingestion_runs, page, page_size, filters)
    return {
        "rows": [_run_view(row) for row in _as_list(result.get("rows"))],
        "filters": filters,
        "sort": sort,
        "sort_links": _sort_links(query, prefix, sort, ["source", "status", "records_read", "records_written", "started_at"]),
        "export_url": _export_url(query, "runs"),
        "page": _page_meta(query, prefix, page, page_size, total),
    }


def _category_table(storage: Storage, query: Any, page_size: int) -> dict[str, Any]:
    prefix = "categories"
    page = _query_page(query, prefix)
    sort = _sort_state(query, prefix, "item_count", "desc")
    filters = {
        "q": _query_value(query, f"{prefix}_q"),
        "needs_rag": _query_value(query, f"{prefix}_needs_rag"),
        "sort": sort["key"],
        "direction": sort["direction"],
    }
    result, page, total = _clamped_paginated_result(storage.paginated_item_categories, page, page_size, filters)
    return {
        "rows": [_category_view(row) for row in _as_list(result.get("rows"))],
        "filters": filters,
        "sort": sort,
        "sort_links": _sort_links(query, prefix, sort, ["category", "item_count", "avg_confidence", "needs_rag"]),
        "export_url": _export_url(query, "categories"),
        "page": _page_meta(query, prefix, page, page_size, total),
    }


def _cluster_table(storage: Storage, query: Any, page_size: int) -> dict[str, Any]:
    prefix = "clusters"
    page = _query_page(query, prefix)
    sort = _sort_state(query, prefix, "item_count", "desc")
    filters = {"q": _query_value(query, f"{prefix}_q"), "sort": sort["key"], "direction": sort["direction"]}
    result, page, total = _clamped_paginated_result(storage.paginated_item_clusters, page, page_size, filters)
    return {
        "rows": [_cluster_view(row) for row in _as_list(result.get("rows"))],
        "filters": filters,
        "sort": sort,
        "sort_links": _sort_links(query, prefix, sort, ["label", "item_count", "avg_unit_price", "states", "total_value"]),
        "export_url": _export_url(query, "clusters"),
        "page": _page_meta(query, prefix, page, page_size, total),
    }


def _knn_table(storage: Storage, query: Any, page_size: int) -> dict[str, Any]:
    prefix = "knn"
    page = _query_page(query, prefix)
    sort = _sort_state(query, prefix, "price_ratio", "desc")
    filters = {"q": _query_value(query, f"{prefix}_q"), "sort": sort["key"], "direction": sort["direction"]}
    result, page, total = _clamped_paginated_result(storage.paginated_knn_review_queue, page, page_size, filters)
    return {
        "rows": [_knn_pair_view(row) for row in _as_list(result.get("rows"))],
        "filters": filters,
        "sort": sort,
        "sort_links": _sort_links(query, prefix, sort, ["item", "neighbor", "unit", "adjusted_price", "price_ratio"]),
        "export_url": _export_url(query, "knn"),
        "page": _page_meta(query, prefix, page, page_size, total),
    }


def _query_value(query: Any, key: str) -> str:
    value = query.get(key, "") if hasattr(query, "get") else ""
    return str(value or "").strip()


def _query_page(query: Any, prefix: str) -> int:
    try:
        return max(1, int(_query_value(query, f"{prefix}_page") or "1"))
    except ValueError:
        return 1


def _sort_state(query: Any, prefix: str, default_key: str, default_direction: str) -> dict[str, str]:
    key = _query_value(query, f"{prefix}_sort") or default_key
    direction = (_query_value(query, f"{prefix}_dir") or default_direction).lower()
    if direction not in {"asc", "desc"}:
        direction = default_direction
    return {"key": key, "direction": direction}


def _sort_links(query: Any, prefix: str, sort: dict[str, str], keys: list[str]) -> dict[str, dict[str, Any]]:
    return {key: _sort_link(query, prefix, key, sort) for key in keys}


def _sort_link(query: Any, prefix: str, key: str, sort: dict[str, str]) -> dict[str, Any]:
    active = sort["key"] == key
    next_direction = "asc" if active and sort["direction"] == "desc" else "desc" if active else "asc"
    params = _query_params(query)
    params[f"{prefix}_sort"] = key
    params[f"{prefix}_dir"] = next_direction
    params[f"{prefix}_page"] = "1"
    return {
        "url": f"?{urlencode(params)}",
        "active": active,
        "direction": sort["direction"] if active else "",
        "next_direction": next_direction,
    }


def _export_url(query: Any, table_key: str) -> str:
    params = {
        key: value
        for key, value in _query_params(query).items()
        if key.startswith(f"{table_key}_") and not key.endswith("_page")
    }
    query_string = urlencode(params)
    return f"/export/{table_key}{'?' + query_string if query_string else ''}"


def _clamped_paginated_result(fetch: Any, page: int, page_size: int, filters: dict[str, str]) -> tuple[dict[str, Any], int, int]:
    result = fetch(page=page, page_size=page_size, **filters)
    total = _int(result.get("total"))
    total_pages = max(1, ceil(total / page_size)) if total else 1
    current = min(max(page, 1), total_pages)
    if current != page:
        result = fetch(page=current, page_size=page_size, **filters)
    return result, current, total


def _page_meta(query: Any, prefix: str, page: int, page_size: int, total: int) -> dict[str, Any]:
    total_pages = max(1, ceil(total / page_size)) if total else 1
    current = min(max(page, 1), total_pages)
    first = ((current - 1) * page_size) + 1 if total else 0
    last = min(current * page_size, total)
    return {
        "prefix": prefix,
        "current": current,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "first": first,
        "last": last,
        "has_previous": current > 1,
        "has_next": current < total_pages,
        "previous_url": _page_url(query, prefix, current - 1) if current > 1 else "",
        "next_url": _page_url(query, prefix, current + 1) if current < total_pages else "",
    }


def _page_url(query: Any, prefix: str, page: int) -> str:
    params = _query_params(query)
    params[f"{prefix}_page"] = str(page)
    return f"?{urlencode(params)}"


def _query_params(query: Any) -> dict[str, str]:
    return {str(key): str(value) for key, value in getattr(query, "items", lambda: [])() if value not in {"", None}}


def _page_copy(active_page: str) -> dict[str, str]:
    pages = {
        "overview": {
            "title": "Compras p\u00fablicas em revis\u00e3o",
            "subtitle": "Resumo executivo do risco, cobertura e material anal\u00edtico pronto.",
        },
        "pipeline": {
            "title": "Pipeline de dados",
            "subtitle": "Camadas de maturidade do dado.",
        },
        "qualidade": {
            "title": "Qualidade Golden",
            "subtitle": "Bloqueios que impedem benchmark confi\u00e1vel.",
        },
        "investigacao": {
            "title": "Alertas",
            "subtitle": "Casos priorizados para revis\u00e3o humana.",
        },
        "vizinhos": {
            "title": "Vizinhos sem\u00e2nticos",
            "subtitle": "Pares compar\u00e1veis usados pelo KNN.",
        },
        "normalizacao": {
            "title": "Categorias",
            "subtitle": "Nomes can\u00f4nicos e necessidade de RAG.",
        },
        "clusters": {
            "title": "Clusters",
            "subtitle": "Grupos compar\u00e1veis por item, unidade e pre\u00e7o.",
        },
        "operacao": {
            "title": "Jobs",
            "subtitle": "Processos ass\u00edncronos e progresso.",
        },
        "ingestoes": {
            "title": "Ingest\u00f5es",
            "subtitle": "Coletas executadas por fonte p\u00fablica.",
        },
    }
    return pages.get(active_page, pages["overview"])


def _page_guidance(
    active_page: str,
    *,
    alerts: int,
    pairs: int,
    categories: int,
    clusters: int,
    jobs: int,
    runs: int,
    comparable: int,
    blocked: int,
    silver_total: int,
) -> dict[str, Any]:
    disclaimer = "Triagem, n\u00e3o acusa\u00e7\u00e3o. Confirme com edital, termo e revis\u00e3o humana."
    pages = {
        "overview": {
            "label": "Leitura executiva",
            "question": "Qual \u00e9 a situa\u00e7\u00e3o geral da base?",
            "plain": (
                "Esta p\u00e1gina resume o volume processado, a parcela compar\u00e1vel e os sinais "
                "estat\u00edsticos que merecem aten\u00e7\u00e3o primeiro."
            ),
            "facts": [
                {"label": "Registros Silver", "value": silver_total},
                {"label": "Itens compar\u00e1veis", "value": comparable},
                {"label": "Alertas ativos", "value": alerts},
            ],
            "read": [
                "Compar\u00e1veis s\u00e3o itens com descri\u00e7\u00e3o e unidade suficientes para benchmark.",
                "Fora do KNN indica registros ainda fracos para compara\u00e7\u00e3o estat\u00edstica confi\u00e1vel.",
                "Alertas combinam pre\u00e7o, recorr\u00eancia, qualidade da descri\u00e7\u00e3o e vizinhos encontrados.",
            ],
            "terms": [
                {"term": "Silver", "definition": "Registro p\u00fablico j\u00e1 normalizado para consulta."},
                {"term": "Golden", "definition": "Registro pronto, ou bloqueado, para compara\u00e7\u00e3o anal\u00edtica."},
                {"term": "KNN", "definition": "Vizinhos mais parecidos usados como base de compara\u00e7\u00e3o."},
                {"term": "Alerta", "definition": "Sinal estat\u00edstico que merece revis\u00e3o documentada."},
            ],
            "limit": disclaimer,
        },
        "pipeline": {
            "label": "Trilha do dado",
            "question": "Em que camada o dado est\u00e1?",
            "plain": "Bronze coleta, Silver normaliza e Golden decide se o item pode ser comparado.",
            "facts": [
                {"label": "Silver", "value": silver_total},
                {"label": "Golden compar\u00e1vel", "value": comparable},
                {"label": "Bloqueios", "value": blocked},
            ],
            "read": [
                "Bronze preserva o dado coletado da fonte p\u00fablica.",
                "Silver padroniza campos como item, unidade, \u00f3rg\u00e3o, fornecedor, data e valor.",
                "Golden decide se o item pode entrar no benchmark ou se precisa de complemento.",
            ],
            "terms": [
                {"term": "Bronze", "definition": "Carga bruta, sem enriquecimento complementar."},
                {"term": "Silver", "definition": "Tabela normalizada para leitura e filtros."},
                {"term": "Golden", "definition": "Base preparada para risco, KNN e relat\u00f3rio audit\u00e1vel."},
                {"term": "Job", "definition": "Etapa ass\u00edncrona com status, progresso e mensagem."},
            ],
            "limit": disclaimer,
        },
        "qualidade": {
            "label": "R\u00e9gua Golden",
            "question": "Por que um item foi bloqueado?",
            "plain": "Esta tela mostra os motivos que impedem benchmark confi\u00e1vel.",
            "facts": [
                {"label": "Bloqueios", "value": blocked},
                {"label": "Compar\u00e1veis", "value": comparable},
                {"label": "Silver", "value": silver_total},
            ],
            "read": [
                "Gen\u00e9rico ou fraco precisa de cat\u00e1logo, complemento ou documento.",
                "Unidade incerta impede normaliza\u00e7\u00e3o de pre\u00e7o.",
                "Escopo amplo deve ser lido no edital antes de comparar.",
            ],
            "terms": [
                {"term": "Bloqueio", "definition": "Registro fora do benchmark por baixa qualidade."},
                {"term": "Golden", "definition": "Camada pronta para risco ou bloqueio justificado."},
                {"term": "Unidade", "definition": "Medida usada para normalizar pre\u00e7o."},
                {"term": "Escopo", "definition": "Objeto amplo que exige documento."},
            ],
            "limit": disclaimer,
        },
        "investigacao": {
            "label": "Fila de revis\u00e3o",
            "question": "Qual alerta revisar primeiro?",
            "plain": "Alertas ordenam risco estat\u00edstico, valor e qualidade da compara\u00e7\u00e3o.",
            "facts": [
                {"label": "Alertas", "value": alerts},
                {"label": "Pares KNN", "value": pairs},
                {"label": "Bloqueados", "value": blocked},
            ],
            "read": [
                "Severidade maior significa prioridade de leitura, n\u00e3o conclus\u00e3o autom\u00e1tica.",
                "Qualidade indica se a descri\u00e7\u00e3o sustenta a compara\u00e7\u00e3o.",
                "Abra o alerta para ver evid\u00eancias, vizinhos e narrativa audit\u00e1vel.",
            ],
            "terms": [
                {"term": "Severidade", "definition": "Peso operacional para ordenar a revis\u00e3o."},
                {"term": "Score", "definition": "For\u00e7a relativa do sinal estat\u00edstico."},
                {"term": "Vizinho", "definition": "Item mais parecido usado no benchmark."},
                {"term": "Mediana", "definition": "Pre\u00e7o central do grupo compar\u00e1vel."},
            ],
            "limit": disclaimer,
        },
        "vizinhos": {
            "label": "KNN",
            "question": "Quais pares distorcem pre\u00e7o?",
            "plain": "Pares mostram itens semanticamente compat\u00edveis com maior diferen\u00e7a de pre\u00e7o.",
            "facts": [
                {"label": "Pares KNN", "value": pairs},
                {"label": "Bloqueados", "value": blocked},
                {"label": "Clusters", "value": clusters},
            ],
            "read": [
                "Unidades incompat\u00edveis n\u00e3o entram no par.",
                "Similaridade sem\u00e2ntica reduz falso vizinho por contexto gen\u00e9rico.",
                "Diferen\u00e7a alta ainda exige especifica\u00e7\u00e3o e documento.",
            ],
            "terms": [
                {"term": "Vizinho", "definition": "Item compat\u00edvel usado como compara\u00e7\u00e3o."},
                {"term": "KNN", "definition": "Busca dos vizinhos mais pr\u00f3ximos."},
                {"term": "Similaridade", "definition": "For\u00e7a do match sem\u00e2ntico."},
                {"term": "Diferen\u00e7a", "definition": "Maior raz\u00e3o entre pre\u00e7os normalizados."},
            ],
            "limit": disclaimer,
        },
        "normalizacao": {
            "label": "Vocabul\u00e1rio do item",
            "question": "Como o item foi categorizado?",
            "plain": "Categorias organizam nomes can\u00f4nicos e marcam itens que pedem RAG.",
            "facts": [
                {"label": "Categorias", "value": categories},
                {"label": "Clusters", "value": clusters},
                {"label": "Pares KNN", "value": pairs},
            ],
            "read": [
                "Categoria \u00e9 uma hip\u00f3tese de nome padronizado para descri\u00e7\u00f5es parecidas.",
                "Confian\u00e7a baixa pede documento ou metadado.",
                "RAG sinaliza item que deve buscar edital, termo de refer\u00eancia ou metadado antes do risco.",
            ],
            "terms": [
                {"term": "Categoria", "definition": "Nome can\u00f4nico candidato para agrupar itens."},
                {"term": "Cluster", "definition": "Grupo de itens parecidos o suficiente para compara\u00e7\u00e3o."},
                {"term": "Unidade", "definition": "Medida de compra que altera totalmente o benchmark."},
                {"term": "RAG", "definition": "Enriquecimento futuro com documentos e contexto textual."},
            ],
            "limit": disclaimer,
        },
        "clusters": {
            "label": "Grupos",
            "question": "Quais itens formam um grupo compar\u00e1vel?",
            "plain": "Clusters agrupam itens por identidade sem\u00e2ntica, unidade e faixa de pre\u00e7o.",
            "facts": [
                {"label": "Clusters", "value": clusters},
                {"label": "Pares KNN", "value": pairs},
                {"label": "Compar\u00e1veis", "value": comparable},
            ],
            "read": [
                "Cada cluster deve representar uma fam\u00edlia compar\u00e1vel.",
                "Faixa larga pode indicar especifica\u00e7\u00e3o ausente.",
                "UFs mostram cobertura geogr\u00e1fica do grupo.",
            ],
            "terms": [
                {"term": "Cluster", "definition": "Grupo de itens compar\u00e1veis."},
                {"term": "Faixa", "definition": "Menor e maior pre\u00e7o normalizado."},
                {"term": "UFs", "definition": "Estados presentes no grupo."},
                {"term": "Item", "definition": "Registro normalizado da compra."},
            ],
            "limit": disclaimer,
        },
        "operacao": {
            "label": "Sa\u00fade operacional",
            "question": "Qual job est\u00e1 rodando?",
            "plain": "Jobs mostram etapa, status e progresso dos processos ass\u00edncronos.",
            "facts": [
                {"label": "Jobs", "value": jobs},
                {"label": "Ingest\u00f5es", "value": runs},
                {"label": "Bloqueios", "value": blocked},
            ],
            "read": [
                "Running indica processamento em andamento; partial pede leitura da mensagem.",
                "Lidos e gravados ajudam a detectar fonte inst\u00e1vel, filtro vazio ou erro de parse.",
                "Progresso mostra a etapa atual sem precisar recalcular tudo para enxergar a fila.",
            ],
            "terms": [
                {"term": "Ingest\u00e3o", "definition": "Coleta de dados da fonte p\u00fablica para Bronze."},
                {"term": "Job", "definition": "Processo rastre\u00e1vel de normaliza\u00e7\u00e3o ou an\u00e1lise."},
                {"term": "Partial", "definition": "Rodou parcialmente e precisa de revis\u00e3o do motivo."},
                {"term": "Gravados", "definition": "Registros aceitos no banco local depois da etapa."},
            ],
            "limit": disclaimer,
        },
        "ingestoes": {
            "label": "Coletas",
            "question": "O que foi coletado da fonte p\u00fablica?",
            "plain": "Ingest\u00f5es mostram fonte, par\u00e2metros, volume lido, volume gravado e erro.",
            "facts": [
                {"label": "Ingest\u00f5es", "value": runs},
                {"label": "Jobs", "value": jobs},
                {"label": "Silver", "value": silver_total},
            ],
            "read": [
                "Lidos maior que gravados pode indicar deduplica\u00e7\u00e3o ou filtro.",
                "Erro preenchido exige reexecu\u00e7\u00e3o ou ajuste do conector.",
                "Par\u00e2metros documentam janela, fonte e limite usado.",
            ],
            "terms": [
                {"term": "Fonte", "definition": "Origem p\u00fablica da coleta."},
                {"term": "Lidos", "definition": "Registros recebidos pela ingest\u00e3o."},
                {"term": "Gravados", "definition": "Registros aceitos no banco local."},
                {"term": "Par\u00e2metros", "definition": "Filtros usados na execu\u00e7\u00e3o."},
            ],
            "limit": disclaimer,
        },
    }
    return pages.get(active_page, pages["overview"])


def _page_path(active_page: str) -> str:
    paths = {
        "overview": "/",
        "pipeline": "/pipeline",
        "qualidade": "/pipeline/qualidade",
        "investigacao": "/investigacao",
        "vizinhos": "/investigacao/vizinhos",
        "normalizacao": "/normalizacao",
        "clusters": "/normalizacao/clusters",
        "operacao": "/operacao",
        "ingestoes": "/operacao/ingestoes",
    }
    return paths.get(active_page, "/")


def _nav_items(active_page: str) -> list[dict[str, str]]:
    items = [
        ("Principal", "overview", "Vis\u00e3o geral", "i-dashboard", "/"),
        ("Dados", "pipeline", "Pipeline", "i-layers", "/pipeline"),
        ("Dados", "qualidade", "Qualidade", "i-database", "/pipeline/qualidade"),
        ("Risco", "investigacao", "Alertas", "i-shield", "/investigacao"),
        ("Risco", "vizinhos", "Vizinhos", "i-network", "/investigacao/vizinhos"),
        ("Normaliza\u00e7\u00e3o", "normalizacao", "Categorias", "i-tags", "/normalizacao"),
        ("Normaliza\u00e7\u00e3o", "clusters", "Clusters", "i-network", "/normalizacao/clusters"),
        ("Opera\u00e7\u00e3o", "operacao", "Jobs", "i-layers", "/operacao"),
        ("Opera\u00e7\u00e3o", "ingestoes", "Ingest\u00f5es", "i-database", "/operacao/ingestoes"),
    ]
    return [
        {"group": group, "key": key, "label": label, "icon": icon, "href": href, "active": key == active_page}
        for group, key, label, icon, href in items
    ]


def _risk_posture(alerts: dict[str, Any]) -> dict[str, str]:
    max_severity = _int(alerts.get("max_severity"))
    alert_count = _int(alerts.get("alerts"))
    if max_severity >= 3:
        return {"label": "Risco crítico", "tone": "critical"}
    if alert_count:
        return {"label": "Risco elevado", "tone": "warning"}
    return {"label": "Sem alerta ativo", "tone": "stable"}


def _knn_pair_view(row: dict[str, Any]) -> dict[str, Any]:
    ratio = _float(row.get("price_ratio"))
    return {
        **row,
        "similarity_display": f"{_float(row.get('similarity')):.2f}",
        "ratio_display": f"{ratio:.1f}x" if ratio >= 1.01 else "alinhado",
        "unit_price_display": _money(row.get("unit_price")),
        "neighbor_unit_price_display": _money(row.get("neighbor_unit_price")),
        "adjusted_unit_price_display": _money(row.get("adjusted_unit_price")),
        "neighbor_adjusted_unit_price_display": _money(row.get("neighbor_adjusted_unit_price")),
    }


def _blocked_view(row: dict[str, Any]) -> dict[str, Any]:
    description = str(row.get("item_description") or "").strip()
    display_description = description
    if not display_description or display_description.upper().startswith("ITEM PNCP"):
        display_description = "Descri\u00e7\u00e3o de item n\u00e3o publicada"
    item_code = str(row.get("item_code") or row.get("item_id") or "").strip()
    reference_parts = [
        str(row.get("state") or "UF N/A"),
        f"codigo {item_code}" if item_code else "",
        str(row.get("supplier_name") or row.get("agency_name") or "").strip(),
    ]
    return {
        **row,
        "display_description": display_description,
        "quality_label": _quality_label(row.get("quality_level")),
        "reference_display": " | ".join(part for part in reference_parts if part),
        "total_value_display": _money(row.get("total_value")),
        "tone": str(row.get("quality_level") or "unknown").replace("_", "-"),
    }


def _job_view(row: dict[str, Any]) -> dict[str, Any]:
    progress = max(0.0, min(_float(row.get("progress")), 100.0))
    return {
        **row,
        "progress_display": f"{progress:.0f}%",
        "progress_style": f"width: {progress:.2f}%",
        "status_tone": str(row.get("status") or "unknown").lower(),
    }


def _cluster_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "avg_unit_price_display": _money(row.get("avg_unit_price")),
        "min_unit_price_display": _money(row.get("min_unit_price")),
        "max_unit_price_display": _money(row.get("max_unit_price")),
        "states_display": ", ".join(str(item) for item in row.get("states", [])) or "N/A",
    }


def _category_view(row: dict[str, Any]) -> dict[str, Any]:
    avg_confidence = _float(row.get("avg_confidence"))
    return {
        **row,
        "confidence_display": f"{avg_confidence * 100:.0f}%",
        "needs_rag": _int(row.get("needs_rag")),
    }


def _alert_view(row: dict[str, Any]) -> dict[str, Any]:
    quality = _dict(row.get("description_quality"))
    risk_type = str(row.get("risk_type") or "")
    return {
        **row,
        "display_title": _display_item(row.get("item_description")),
        "risk_label": _risk_label(risk_type),
        "detail_href": f"/investigacao/alertas/{row.get('id')}",
        "score_display": f"{_float(row.get('score')):.2f}",
        "total_value_display": _money(row.get("total_value")),
        "quality_level": quality.get("level", "unknown"),
    }


def _risk_type_view(row: dict[str, Any]) -> dict[str, Any]:
    label = _risk_label(row.get("risk_type"))
    return {**row, "label": label}


def _comparison_rows(evidence: dict[str, Any], adjusted_unit_price: float) -> list[dict[str, Any]]:
    rows = []
    for neighbor in _as_list(evidence.get("neighbors")):
        adjusted_neighbor = adjusted_price_for_unit(str(neighbor.get("unit") or ""), _float(neighbor.get("unit_price")))
        ratio = adjusted_unit_price / adjusted_neighbor if adjusted_unit_price and adjusted_neighbor else 0.0
        rows.append(
            {
                **neighbor,
                "unit_price_display": _money(neighbor.get("unit_price")),
                "adjusted_unit_price": adjusted_neighbor,
                "adjusted_unit_price_display": _money(adjusted_neighbor),
                "similarity_display": f"{_float(neighbor.get('similarity')):.2f}",
                "ratio_display": f"{ratio:.1f}x" if ratio else "N/A",
                "state_display": str(neighbor.get("state") or "UF N/A"),
            }
        )
    return rows


def _report_lines(
    detail: dict[str, Any],
    evidence: dict[str, Any],
    comparison_rows: list[dict[str, Any]],
) -> list[dict[str, str]]:
    ratio = _float(evidence.get("ratio"))
    adjusted = _money(evidence.get("adjusted_unit_price"))
    median = _money(evidence.get("neighbor_median"))
    item = _display_item(detail.get("item_description"))
    return [
        {
            "label": "Fato observado",
            "text": f"{item} foi registrado com preço normalizado de {adjusted}.",
        },
        {
            "label": "Comparação",
            "text": f"A mediana dos {len(comparison_rows)} vizinhos comparáveis ficou em {median}.",
        },
        {
            "label": "Sinal estatístico",
            "text": f"O item ficou {ratio:.1f}x acima da mediana usada pelo motor de anomalias.",
        },
        {
            "label": "Cuidado de auditoria",
            "text": "O alerta prioriza revisão humana; edital, termo de referência e especificações ainda precisam confirmar equivalência real.",
        },
    ]


def _quality_rows(golden: dict[str, Any], scope_total: int) -> list[dict[str, Any]]:
    return [
        {"label": "Escopo PNCP", "value": scope_total, "detail": "objeto de contratação", "tone": "neutral"},
        {"label": "Descrição ausente", "value": _int(golden.get("missing")), "detail": "sem item publicado", "tone": "critical"},
        {"label": "Genéricos", "value": _int(golden.get("generic")), "detail": "sem catálogo", "tone": "warning"},
        {"label": "Fracos", "value": _int(golden.get("weak")), "detail": "texto insuficiente", "tone": "warning"},
        {"label": "Escopo amplo", "value": _int(golden.get("broad_scope")), "detail": "exige documento", "tone": "warning"},
        {"label": "Exigem especificação", "value": _int(golden.get("spec_required")), "detail": "SKU incompleto", "tone": "warning"},
        {"label": "Unidade incerta", "value": _int(golden.get("unit_unknown")), "detail": "fora da régua", "tone": "critical"},
    ]


def _risk_label(value: Any) -> str:
    labels = {
        "price_outlier": "Preço fora da curva",
        "supplier_concentration": "Fornecedor recorrente",
        "fragmented_purchase": "Possível fracionamento",
    }
    return labels.get(str(value or ""), str(value or "Risco").replace("_", " ").title())


def _display_item(value: Any) -> str:
    text = str(value or "").strip()
    return text if text else "Item sem descrição publicada"


def _run_view(row: dict[str, Any]) -> dict[str, Any]:
    started = str(row.get("started_at") or "").replace("T", " ")
    finished = str(row.get("finished_at") or "").replace("T", " ")
    return {
        **row,
        "status_tone": str(row.get("status") or "unknown").lower(),
        "records_display": f"{_int(row.get('records_read'))} / {_int(row.get('records_written'))}",
        "parameters_display": _compact_params(_dict(row.get("parameters"))),
        "window_display": f"{started[:16]} -> {finished[:16] if finished else 'em aberto'}",
        "error_display": str(row.get("error") or "sem erro"),
    }


def _compact_params(params: dict[str, Any]) -> str:
    if not params:
        return "sem parametros"
    priority = [
        "source",
        "start",
        "end",
        "start_year",
        "end_year",
        "window_days",
        "max_pages",
        "limit",
        "limit_per_year",
        "analyze",
        "cluster",
        "categorize",
    ]
    parts = []
    for key in priority:
        value = params.get(key)
        if value not in {"", None, False}:
            parts.append(f"{key}={value}")
    if not parts:
        for key, value in sorted(params.items())[:4]:
            if value not in {"", None, False}:
                parts.append(f"{key}={value}")
    return " | ".join(parts[:5]) or "sem parametros"


def _quality_label(value: Any) -> str:
    labels = {
        "missing": "Descri\u00e7\u00e3o ausente",
        "generic": "Descri\u00e7\u00e3o gen\u00e9rica",
        "weak": "Descri\u00e7\u00e3o fraca",
        "broad_scope": "Escopo amplo",
        "spec_required": "Exige especifica\u00e7\u00e3o",
        "unit_unknown": "Unidade incerta",
        "procurement_scope": "Escopo de contrata\u00e7\u00e3o",
    }
    return labels.get(str(value or "unknown"), "Qualidade indefinida")


def _money(value: Any) -> str:
    amount = _float(value)
    return f"R$ {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _compact_money(value: Any) -> str:
    amount = _float(value)
    if abs(amount) >= 1_000_000_000:
        return f"R$ {amount / 1_000_000_000:.1f} bi".replace(".", ",")
    if abs(amount) >= 1_000_000:
        return f"R$ {amount / 1_000_000:.1f} mi".replace(".", ",")
    if abs(amount) >= 1_000:
        return f"R$ {amount / 1_000:.1f} mil".replace(".", ",")
    return _money(amount)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _csv_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return str(value)
