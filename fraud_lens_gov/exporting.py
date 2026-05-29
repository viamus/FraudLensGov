from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable


def export_alerts(rows: list[dict[str, object]], output_path: Path, output_format: str) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "json":
        output_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        return output_path
    if output_format == "csv":
        _write_csv(rows, output_path)
        return output_path
    if output_format == "md":
        output_path.write_text(_markdown(rows), encoding="utf-8")
        return output_path
    raise ValueError(f"Unsupported export format: {output_format}")


def _write_csv(rows: list[dict[str, object]], output_path: Path) -> None:
    fieldnames = [
        "alert_id",
        "risk_type",
        "severity",
        "score",
        "title",
        "explanation",
        "genai_explanation",
        "item_id",
        "source",
        "source_record_id",
        "procurement_id",
        "item_code",
        "item_description",
        "unit",
        "quantity",
        "unit_price",
        "total_value",
        "currency",
        "agency_name",
        "agency_id",
        "supplier_name",
        "supplier_id",
        "city",
        "state",
        "procurement_date",
        "modality",
        "portal_url",
        "evidence",
        "created_at",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            csv_row = dict(row)
            csv_row["evidence"] = json.dumps(row.get("evidence", {}), ensure_ascii=False, sort_keys=True)
            writer.writerow({field: csv_row.get(field, "") for field in fieldnames})


def _markdown(rows: Iterable[dict[str, object]]) -> str:
    lines = [
        "# FraudLensGov - Alertas Auditaveis",
        "",
        "Este relatorio lista sinais de risco para triagem humana. Ele nao declara fraude.",
        "",
    ]
    for index, row in enumerate(rows, start=1):
        evidence = json.dumps(row.get("evidence", {}), ensure_ascii=False, indent=2, sort_keys=True)
        lines.extend(
            [
                f"## {index}. {row.get('title', '')}",
                "",
                f"- Tipo: `{row.get('risk_type', '')}`",
                f"- Severidade: `{row.get('severity', '')}`",
                f"- Score: `{row.get('score', '')}`",
                f"- Item: {row.get('item_description', '')}",
                f"- Orgao: {row.get('agency_name', '')}",
                f"- Fornecedor: {row.get('supplier_name', '') or 'Nao informado'}",
                f"- Valor total: {row.get('currency', 'BRL')} {row.get('total_value', '')}",
                f"- Fonte: {row.get('source', '')} / {row.get('source_record_id', '')}",
                f"- URL: {row.get('portal_url', '')}",
                "",
                row.get("genai_explanation") or row.get("explanation") or "",
                "",
                "```json",
                evidence,
                "```",
                "",
            ]
        )
    return "\n".join(str(line) for line in lines)
