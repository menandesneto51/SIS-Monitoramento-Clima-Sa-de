from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import textwrap

import pandas as pd

from sisclima.core.config import APP_CONFIG, env, as_bool
from sisclima.core.db import read_table, table_exists
from sisclima.core.logging_utils import get_logger
from sisclima.alerts.notifier import send_email, send_telegram

log = get_logger(__name__)


def _read(name: str) -> pd.DataFrame:
    try:
        if not table_exists(name):
            return pd.DataFrame()
        df = read_table(name)
        return df if df is not None else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def build_report_context() -> dict:
    resumo = _read("resumo_situacao_atual")
    muni = _read("resumo_municipal_atual")
    pront = _read("prontidao_municipal")
    aq = _read("qualidade_ar_municipal")
    rec = _read("recomendacoes_operacionais")
    terr = pd.DataFrame()
    try:
        from sisclima.engines.vigibarragens_clima import sintese_territorial

        terr_src = pront if not pront.empty else muni
        terr = sintese_territorial(terr_src)
    except Exception as exc:  # noqa: BLE001
        log.warning("Síntese territorial do relatório: %s", exc)
        terr = {"ok": False, "texto": str(exc)}

    top = pd.DataFrame()
    if not muni.empty and "score" in muni.columns:
        sort_cols = ["score"]
        if "indice_vulnerabilidade_calor" in muni.columns:
            sort_cols.append("indice_vulnerabilidade_calor")
        top = muni.sort_values(sort_cols, ascending=False).head(15)

    farm = []
    if not muni.empty:
        for col in ("acao_farmaceutica_municipal", "acao_farmaceutica_estadual", "orientacao_mascara_iqa"):
            if col in muni.columns:
                farm.append({"campo": col, "amostra": str(muni[col].dropna().astype(str).head(1).to_list()[:1])})

    cenario = {}
    if not pront.empty and "cenario_dominante" in pront.columns:
        vc = pront["cenario_dominante"].astype(str).value_counts().head(6)
        cenario = vc.to_dict()

    return {
        "resumo_estado": resumo.tail(1).to_dict(orient="records")[0] if not resumo.empty else {},
        "top_municipios": top.to_dict(orient="records"),
        "qualidade_ar": aq.tail(20).to_dict(orient="records") if not aq.empty else [],
        "recomendacoes": rec.tail(20).to_dict(orient="records") if not rec.empty else [],
        "territorial": terr if isinstance(terr, dict) else {},
        "cenarios_prontidao": cenario,
        "n_municipios": 0 if muni.empty else (int(muni["cod_ibge"].nunique()) if "cod_ibge" in muni.columns else len(muni)),
    }


def deterministic_report(ctx: dict) -> str:
    est = ctx.get("resumo_estado", {}) or {}
    nivel = str(est.get("nivel", "indisponível")).upper()
    municipio_critico = est.get("municipio", "não definido")
    motivos = str(est.get("motivo", "sem motivos registrados"))
    data = est.get("data_referencia") or datetime.now().date().isoformat()
    n_mun = ctx.get("n_municipios") or "—"
    top = ctx.get("top_municipios", [])
    linhas_top = []
    for r in top[:10]:
        extra = []
        for k, lab in (("n_aldeias", "ald"), ("n_quilombos", "quil"), ("n_assentamentos", "ass")):
            try:
                v = int(float(r.get(k) or 0))
            except Exception:
                v = 0
            if v:
                extra.append(f"{v} {lab}")
        cen = r.get("cenario_dominante") or ""
        terr = f" | territórios: {', '.join(extra)}" if extra else ""
        cen_txt = f" | cenário {cen}" if cen else ""
        linhas_top.append(
            f"- {r.get('municipio')}: nível {r.get('nivel')} | score {r.get('score')}{cen_txt}{terr} | {str(r.get('motivo',''))[:140]}"
        )
    if not linhas_top:
        linhas_top.append("- Sem municípios classificados no ciclo atual.")
    recs = ctx.get("recomendacoes", [])
    linhas_rec = []
    for r in recs[-8:]:
        linhas_rec.append(f"- {r.get('eixo','Operacional')}: {r.get('recomendacao')}")
    if not linhas_rec:
        linhas_rec.append("- Validar fontes de dados e manter rotina de monitoramento até novo ciclo.")

    terr = ctx.get("territorial") or {}
    terr_txt = terr.get("texto") or "Cadastro Vigibarragens ainda não cruzado nesta rodada."
    top_terr = terr.get("top") or []
    linhas_terr = "\n    ".join(f"- {x}" for x in top_terr) if top_terr else "- Sem ranking territorial nesta rodada."

    cen = ctx.get("cenarios_prontidao") or {}
    if cen:
        linhas_cen = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in cen.items())
    else:
        linhas_cen = "sem prontidão municipal persistida"

    return textwrap.dedent(
        f"""
    BOLETIM OPERACIONAL ARARAS MT — Desenvolvido pelo CIEVS · SES-MT
    Clima, saúde, prontidão e povos/territórios vulneráveis
    Data de referência: {data}
    Recorte: {n_mun} municípios IBGE-MT

    1. SITUAÇÃO GERAL
    Nível estadual consolidado: {nivel}. Município sentinela mais crítico: {municipio_critico}.

    2. PRINCIPAIS GATILHOS
    {motivos}

    3. PRONTIDÃO CLIMÁTICA (cenário dominante)
    {linhas_cen}
    Fase 1 MT: seca/estiagem, baixa umidade e queimadas/fumaça. A IA só aplica a matriz validada — não prescreve medicamento.

    4. POVOS E TERRITÓRIOS VULNERÁVEIS (Vigibarragens)
    {terr_txt}
    Municípios com maior carga territorial:
    {linhas_terr}
    Fontes: FUNAI (aldeias), Palmares (quilombos certificados), INCRA (assentamentos), SNISB (barragens DPA). Distância ao eixo Manso–Cuiabá não é polígono de inundação.

    5. MUNICÍPIOS PRIORITÁRIOS
    {chr(10).join(linhas_top)}

    6. RECOMENDAÇÕES OPERACIONAIS
    {chr(10).join(linhas_rec)}
    - Assistência farmacêutica: conferir CBAF municipal e SAF/CEME estadual conforme IQA, seca e cheia (máscara PFF2 segundo PM2,5).
    - SESAI/DSEI nas aldeias; APS rural em quilombos e assentamentos; Defesa Civil se DPA alto + cheia.

    7. ENCAMINHAMENTO
    Validar no painel ARARAS MT (Prontidão climática e Mapas). Não enviar alerta automático sem decisão humana.
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
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048},
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
    if model.startswith("gemini-2.0-flash"):
        model = "gemini-2.5-flash"
    if not api_key:
        return None

    prompt = (
        "Você é assessoria técnica do ARARAS MT (CIEVS/SES-MT). "
        "Gere boletim operacional objetivo, sem inventar dados, usando apenas o JSON. "
        "Inclua prontidão climática e povos/territórios (Vigibarragens). "
        "Não prescreva fármacos. Distância ao eixo de barragem não é cota de inundação.\n\n"
        + json.dumps(ctx, ensure_ascii=False, default=str)[:8000]
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
    out = out_dir / f"boletim_araras_mt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    out.write_text(body, encoding="utf-8")
    if send:
        subject = f"ARARAS MT | Boletim {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        send_email(subject, body)
        send_telegram(body[:3900])
    return out
