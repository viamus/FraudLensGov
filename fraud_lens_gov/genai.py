from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import replace

from .models import Alert


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


def enrich_alerts_with_genai(alerts: list[Alert]) -> list[Alert]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return [replace(alert, genai_explanation=_fallback_explanation(alert)) for alert in alerts]

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
    return [replace(alert, genai_explanation=_call_openai(alert, api_key, model)) for alert in alerts]


def _fallback_explanation(alert: Alert) -> str:
    return (
        "Explicacao deterministica: este alerta foi gerado por regra estatistica local. "
        f"Tipo={alert.risk_type}; severidade={alert.severity}; score={alert.score:.2f}. "
        "Revise a evidencia, compare com documentos originais e trate o resultado como triagem."
    )


def _call_openai(alert: Alert, api_key: str, model: str) -> str:
    prompt = {
        "risk_type": alert.risk_type,
        "severity": alert.severity,
        "score": alert.score,
        "title": alert.title,
        "rule_explanation": alert.explanation,
        "evidence": alert.evidence,
    }
    body = {
        "model": model,
        "instructions": (
            "Voce e um analista de controle publico. Explique alertas de risco em licitacoes "
            "sem acusar fraude. Seja objetivo, cite evidencias numericas e recomende proximos passos."
        ),
        "input": (
            "Explique o alerta abaixo em portugues do Brasil com: resumo, evidencias, "
            "hipoteses benignas possiveis e proximas verificacoes.\n\n"
            + json.dumps(prompt, ensure_ascii=False)
        ),
        "max_output_tokens": 600,
    }
    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return f"Falha ao chamar OpenAI; mantendo explicacao local. Erro: {exc}"
    return _extract_response_text(payload) or _fallback_explanation(alert)


def _extract_response_text(payload: dict[str, object]) -> str:
    output = payload.get("output")
    if not isinstance(output, list):
        return ""
    chunks: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    return "\n".join(chunks).strip()
