from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import render

from fraud_lens_gov.storage import Storage
from fraud_lens_gov.unit_normalization import adjusted_price_for_unit


def dashboard(request):
    return _render_dashboard(request, "overview")


def pipeline_page(request):
    return _render_dashboard(request, "pipeline")


def investigation_page(request):
    return _render_dashboard(request, "investigacao")


def alert_detail_page(request, alert_id: str):
    storage = _storage()
    detail = storage.alert_detail(alert_id)
    if detail is None:
        raise Http404("Alert not found")
    summary = storage.dashboard_summary()
    return render(request, "audit_ui/alert_detail.html", _alert_detail_context(summary, detail))


def normalization_page(request):
    return _render_dashboard(request, "normalizacao")


def operation_page(request):
    return _render_dashboard(request, "operacao")


def _render_dashboard(request, active_page: str):
    summary = _storage().dashboard_summary()
    return render(request, "audit_ui/dashboard.html", _dashboard_context(summary, active_page))


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


def _storage() -> Storage:
    storage = Storage(Path(settings.FRAUDLENS_DB))
    storage.init_schema()
    return storage


def _json(payload: dict[str, Any]) -> JsonResponse:
    return JsonResponse(payload, json_dumps_params={"ensure_ascii": False, "indent": 2})


def _dashboard_context(summary: dict[str, Any], active_page: str = "overview") -> dict[str, Any]:
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
    jobs = [_job_view(row) for row in _as_list(summary.get("pipeline_jobs"))]
    clusters = [_cluster_view(row) for row in _as_list(summary.get("top_clusters"))]
    categories = [_category_view(row) for row in _as_list(summary.get("top_categories"))]
    risk_types = [_risk_type_view(row) for row in _as_list(summary.get("risk_types"))]
    top_alerts = [_alert_view(row) for row in _as_list(summary.get("top_alerts"))]
    ingestion_runs = [_run_view(row) for row in _as_list(summary.get("ingestion_runs"))]
    knn_pairs = [_knn_pair_view(row) for row in pairs]
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
    return {
        "active_page": active_page,
        "page_title": page_copy["title"],
        "page_subtitle": page_copy["subtitle"],
        "nav_items": _nav_items(active_page),
        "posture": _risk_posture(alerts),
        "metrics": [
            {"label": "Silver total", "value": _int(silver.get("total")), "note": "registros normalizados"},
            {"label": "Comparáveis", "value": comparable, "note": "aptos para benchmark"},
            {"label": "Fora do KNN", "value": blocked_total + scope_total, "note": f"{scope_total} objetos PNCP"},
            {"label": "Pares KNN", "value": len(pairs), "note": f"{_int(cluster_totals.get('neighbor_edges'))} arestas"},
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
        "knn_pairs": knn_pairs,
        "visible_alerts": top_alerts[:5] if active_page == "overview" else top_alerts[:12],
        "visible_jobs": jobs[:3] if active_page == "overview" else jobs[:8],
        "visible_knn_pairs": knn_pairs[:8],
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


def _page_copy(active_page: str) -> dict[str, str]:
    pages = {
        "overview": {
            "title": "Compras p\u00fablicas em revis\u00e3o",
            "subtitle": "Resumo executivo do risco, cobertura e material anal\u00edtico pronto.",
        },
        "pipeline": {
            "title": "Pipeline de dados",
            "subtitle": "Camadas Bronze, Silver e Golden com progresso observ\u00e1vel.",
        },
        "investigacao": {
            "title": "Investiga\u00e7\u00e3o",
            "subtitle": "Alertas estat\u00edsticos e pares KNN que precisam de revis\u00e3o humana.",
        },
        "normalizacao": {
            "title": "Normaliza\u00e7\u00e3o e categorias",
            "subtitle": "Categorias candidatas, clusters e fila futura para RAG.",
        },
        "operacao": {
            "title": "Opera\u00e7\u00e3o",
            "subtitle": "Jobs, ingest\u00f5es recentes e sa\u00fade do processamento local.",
        },
    }
    return pages.get(active_page, pages["overview"])


def _nav_items(active_page: str) -> list[dict[str, str]]:
    items = [
        ("overview", "Vis\u00e3o geral", "i-dashboard", "/"),
        ("pipeline", "Pipeline", "i-layers", "/pipeline"),
        ("investigacao", "Investiga\u00e7\u00e3o", "i-shield", "/investigacao"),
        ("normalizacao", "Normaliza\u00e7\u00e3o", "i-tags", "/normalizacao"),
        ("operacao", "Opera\u00e7\u00e3o", "i-database", "/operacao"),
    ]
    return [
        {"key": key, "label": label, "icon": icon, "href": href, "active": key == active_page}
        for key, label, icon, href in items
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
    return {**row, "status_tone": str(row.get("status") or "unknown").lower()}


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
