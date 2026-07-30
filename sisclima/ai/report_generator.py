from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import textwrap

import pandas as pd

from sisclima.core.config import APP_CONFIG, env, as_bool
from sisclima.core.db import read_table
from sisclima.core.logging_utils import get_logger
from sisclima.alerts.notifier import send_email, send_telegram

log = get_logger(__name__)


def build_report_context() -> dict:
    resumo = read_table("resumo_situacao_atual")
    muni = read_table("resumo_municipal_atual")
    aq = read_table("qualidade_ar_municipal")
    rec = read_table("recomendacoes_operacionais")
    top = pd.DataFrame()
    if not muni.empty and "score" in muni.columns:
        top = muni.sort_values(
            ["score", "indice_vulnerabilidade_calor" if "indice_vulnerabilidade_calor" in muni.columns else "score"],
            ascending=False,
        ).head(15)
    return {
        "resumo_estado": resumo.tail(1).to_dict(orient="records")[0] if not resumo.empty else {},
        "top_municipios": top.to_dict(orient="records"),
        "qualidade_ar": aq.tail(20).to_dict(orient="records") if not aq.empty else [],
        "recomendacoes": rec.tail(20).to_dict(orient="records") if not rec.empty else [],
    }


def deterministic_report(ctx: dict) -> str:
    est = ctx.get("resumo_estado", {}) or {}
    nivel = str(est.get("nivel", "indisponível")).upper()
    municipio_critico = est.get("municipio", "não definido")
    motivos = str(est.get("motivo", "sem motivos registrados"))
    data = est.get("data_referencia") or datetime.now().date().isoformat()
    top = ctx.get("top_municipios", [])
    linhas_top = []
    for r in top[:10]:
        linhas_top.append(
            f"- {r.get('municipio')}: nível {r.get('nivel')} | score {r.get('score')} | {str(r.get('motivo',''))[:180]}"
        )
    if not linhas_top:
        linhas_top.append("- Sem municípios classificados no ciclo atual.")
    recs = ctx.get("recomendacoes", [])
    linhas_rec = []
    for r in recs[-8:]:
        linhas_rec.append(f"- {r.get('eixo','Operacional')}: {r.get('recomendacao')}")
    if not linhas_rec:
        linhas_rec.append("- Validar fontes de dados e manter rotina de monitoramento até novo ciclo.")
    return textwrap.dedent(
        f"""
    BOLETIM OPERACIONAL SIS-MT CLIMA-SAÚDE
    Data de referência: {data}

    1. SITUAÇÃO GERAL
    O nível estadual consolidado no ciclo atual é {nivel}. O município sentinela mais crítico para composição estadual foi {municipio_critico}.

    2. PRINCIPAIS GATILHOS
    {motivos}

    3. MUNICÍPIOS PRIORITÁRIOS
    {chr(10).join(linhas_top)}

    4. RECOMENDAÇÕES OPERACIONAIS
    {chr(10).join(linhas_rec)}

    5. ENCAMINHAMENTO
    Recomenda-se manter a extração em tempo real, validar a consistência municipal das bases assistenciais e atualizar os contatos de alerta para cada regional de saúde.
    """
    ).strip()


def _call_gemini_native(api_key: str, model: str, prompt: str) -> str | None:
    import requests

    model_id = model or "gemini-2.0-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent"
    r = requests.post(
        url,
        params={"key": api_key},
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1200},
        },
        timeout=90,
    )
    r.raise_for_status()
    data = r.json()
    parts = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [])
    )
    texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
    out = "\n".join(t for t in texts if t).strip()
    return out or None


def _call_openai_compatible(api_url: str, api_key: str, model: str, prompt: str) -> str | None:
    import requests

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    r = requests.post(api_url, headers=headers, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content") or data.get("text")


def maybe_llm_report(ctx: dict) -> str | None:
    """Camada opcional de IA. Suporta Gemini nativo e endpoints estilo OpenAI."""
    if not as_bool(env("USE_LLM_REPORT", "false")) and not as_bool(env("USE_AI_ALERT_TEXT", "false")):
        return None
    api_url = (env("LLM_API_URL") or "").strip()
    api_key = env("LLM_API_KEY")
    model = (env("LLM_MODEL") or "gemini-2.5-flash").strip()
    # Modelos 2.0 descontinuados na API → promove automaticamente
    if model.startswith("gemini-2.0-flash"):
        model = "gemini-2.5-flash"
    if not api_key:
        return None

    prompt = (
        "Você é uma assessoria técnica de vigilância em saúde (CIEVS/SES-MT). "
        "Gere texto operacional objetivo, sem inventar dados, usando apenas o JSON abaixo.\n\n"
        + json.dumps(ctx, ensure_ascii=False, default=str)[:12000]
    )
    try:
        use_gemini = (
            not api_url
            or "generativelanguage.googleapis.com" in api_url.lower()
            or str(model).lower().startswith("gemini")
        )
        if use_gemini:
            return _call_gemini_native(api_key, model, prompt)
        return _call_openai_compatible(api_url, api_key, model, prompt)
    except Exception as e:
        log.warning("Falha no relatório via IA: %s", e)
        return None


def generate_daily_report(send: bool = False) -> Path:
    ctx = build_report_context()
    body = maybe_llm_report(ctx) or deterministic_report(ctx)
    out_dir = APP_CONFIG.root / "exports" / "relatorios"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"boletim_sis_mt_clima_saude_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    out.write_text(body, encoding="utf-8")
    if send:
        subject = f"SIS-MT Clima-Saúde | Boletim {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        send_email(subject, body)
        send_telegram(body[:3900])
    return out
