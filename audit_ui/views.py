from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import render

from fraud_lens_gov.storage import Storage


def dashboard(request):
    summary = _storage().dashboard_summary()
    return render(request, "audit_ui/dashboard.html", _dashboard_context(summary))


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


def _dashboard_context(summary: dict[str, Any]) -> dict[str, Any]:
    totals = _dict(summary.get("totals"))
    alerts = _dict(summary.get("alerts"))
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
    risk_types = [_risk_type_view(row) for row in _as_list(summary.get("risk_types"))]
    top_alerts = [_alert_view(row) for row in _as_list(summary.get("top_alerts"))]
    ingestion_runs = [_run_view(row) for row in _as_list(summary.get("ingestion_runs"))]
    comparable = _int(golden.get("comparable"))
    blocked_total = _int(golden.get("missing")) + _int(golden.get("generic")) + _int(golden.get("weak"))
    scope_total = _int(golden.get("procurement_scope"))

    return {
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
        "quality": [
            {"label": "Escopo PNCP", "value": scope_total},
            {"label": "Descrição ausente", "value": _int(golden.get("missing"))},
            {"label": "Genéricos", "value": _int(golden.get("generic"))},
            {"label": "Fracos", "value": _int(golden.get("weak"))},
        ],
        "knn_pairs": [_knn_pair_view(row) for row in pairs],
        "blocked_items": [_blocked_view(row) for row in blocked],
        "jobs": jobs,
        "clusters": clusters,
        "risk_types": risk_types,
        "top_alerts": top_alerts,
        "ingestion_runs": ingestion_runs,
        "db_path": str(settings.FRAUDLENS_DB),
    }


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


def _alert_view(row: dict[str, Any]) -> dict[str, Any]:
    quality = _dict(row.get("description_quality"))
    return {
        **row,
        "score_display": f"{_float(row.get('score')):.2f}",
        "total_value_display": _money(row.get("total_value")),
        "quality_level": quality.get("level", "unknown"),
    }


def _risk_type_view(row: dict[str, Any]) -> dict[str, Any]:
    label = str(row.get("risk_type") or "").replace("_", " ").title()
    return {**row, "label": label}


def _run_view(row: dict[str, Any]) -> dict[str, Any]:
    return {**row, "status_tone": str(row.get("status") or "unknown").lower()}


def _quality_label(value: Any) -> str:
    labels = {
        "missing": "Descri\u00e7\u00e3o ausente",
        "generic": "Descri\u00e7\u00e3o gen\u00e9rica",
        "weak": "Descri\u00e7\u00e3o fraca",
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
