"""Alertas VIGIA completos — Estado, Regionais e Cuiabá.

Os três tipos previstos pelo painel VIGIA:
1) ESTADO — consolidado estadual
2) REGIONAIS — regionais de saúde com municípios em alerta
3) CUIABÁ — alerta municipal focado na capital
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from sisclima.alerts.notifier import dispatch_alert
from sisclima.core.config import env, as_bool
from sisclima.core.db import sqlite_conn
from sisclima.core.logging_utils import get_logger
from sisclima.engines.recommendations import recommendations_for_stage
from sisclima.public.exporter import _build_status_alertas
from sisclima.utils.dates import now_iso

log = get_logger(__name__)

ALERT_TYPES = {
    "estado": "TIPO 1/4 — ESTADO (SES/CIEVS)",
    "regional": "TIPO 2/4 — REGIONAL (ERS)",
    "municipal": "TIPO 3/4 — MUNICIPAL",
    "cuiaba": "TIPO 4/4 — CUIABÁ (capital)",
}

# Ícones Unicode (Telegram/e-mail texto). Mantém leitura operacional CIEVS/SES-MT.
NIVEL_ICONS = {
    "verde": "🟢",
    "amarela": "🟡",
    "laranja": "🟠",
    "vermelha": "🔴",
    "roxa": "🟣",
}
TIPO_ICONS = {
    "estado": "🗺️",
    "regional": "🏥",
    "municipal": "📍",
    "cuiaba": "🏙️",
}

SCORE_BY_NIVEL = {
    "verde": 0,
    "amarela": 1,
    "laranja": 2,
    "vermelha": 3,
    "roxa": 4,
}


def _nivel_icon(nivel: str | None) -> str:
    key = str(nivel or "").strip().lower()
    return NIVEL_ICONS.get(key, "⚪")


def _nivel_label(nivel: str | None) -> str:
    raw = str(nivel or "indisponível").strip()
    icon = _nivel_icon(raw)
    return f"{icon} {raw.upper()}"


def _section(title: str, icon: str = "▪️") -> str:
    return f"{icon} {title}"


def _bullet(icon: str, text: str) -> str:
    return f"{icon} {text}"


def _redact_secrets(text: str) -> str:
    out = str(text)
    for key_name in ("GEMINI_API_KEY", "LLM_API_KEY", "TELEGRAM_BOT_TOKEN", "SMTP_PASSWORD", "DW_PASSWORD"):
        val = env(key_name)
        if val:
            out = out.replace(str(val), "***")
    # padrões comuns de chave Google
    import re
    out = re.sub(r"AIza[0-9A-Za-z\-_]{20,}", "AIza***", out)
    out = re.sub(r"key=[^&\s]+", "key=***", out)
    return out


def _requests_verify() -> bool:
    """Em rede corporativa com proxy SSL, use ALERT_SSL_VERIFY=false."""
    return as_bool(env("ALERT_SSL_VERIFY", "true"), True)


def _enrich_regional(resumo_mun: pd.DataFrame) -> pd.DataFrame:
    """Garante coluna regional_saude no resumo, buscando em CSVs públicos se necessário."""
    if resumo_mun is None or resumo_mun.empty:
        return pd.DataFrame()
    out = resumo_mun.copy()
    has_reg = "regional_saude" in out.columns and out["regional_saude"].notna().any()
    if has_reg:
        bad = out["regional_saude"].astype(str).str.strip().str.lower().isin(
            {"", "nan", "none", "sem regional informada", "regional não informada"}
        )
        if (~bad).any():
            return out

    from sisclima.core.config import ROOT

    candidates = [
        ROOT / "data" / "public" / "ops_resumo_operacional_cnes.csv",
        ROOT / "data" / "public" / "geocalor_cardioresp_rr_municipal_v11_12.csv",
        ROOT / "data" / "public" / "geocalor_cuiaba_cardioresp_v11_12.csv",
    ]
    ref = pd.DataFrame()
    for path in candidates:
        if not path.exists():
            continue
        try:
            tmp = pd.read_csv(path, dtype=str)
        except Exception:
            continue
        cols = {c.lower(): c for c in tmp.columns}
        reg_c = cols.get("regional_saude") or cols.get("regional") or cols.get("regiao_saude")
        ibge_c = cols.get("cod_ibge")
        mun_c = cols.get("municipio")
        if not reg_c:
            continue
        keep = [c for c in [ibge_c, mun_c, reg_c] if c]
        ref = tmp[keep].drop_duplicates()
        ref = ref.rename(columns={reg_c: "regional_saude"})
        if ibge_c:
            ref = ref.rename(columns={ibge_c: "cod_ibge"})
        if mun_c:
            ref = ref.rename(columns={mun_c: "municipio"})
        if not ref.empty:
            break
    if ref.empty:
        if "regional_saude" not in out.columns:
            out["regional_saude"] = "Sem regional informada"
        return out

    if "cod_ibge" in out.columns and "cod_ibge" in ref.columns:
        out["cod_ibge"] = out["cod_ibge"].astype(str).str.extract(r"(\d+)")[0].str.zfill(7)
        ref["cod_ibge"] = ref["cod_ibge"].astype(str).str.extract(r"(\d+)")[0].str.zfill(7)
        out = out.drop(columns=["regional_saude"], errors="ignore").merge(
            ref[["cod_ibge", "regional_saude"]].drop_duplicates("cod_ibge"),
            on="cod_ibge",
            how="left",
        )
    elif "municipio" in out.columns and "municipio" in ref.columns:
        out["_mun_key"] = out["municipio"].astype(str).str.lower().str.strip()
        ref["_mun_key"] = ref["municipio"].astype(str).str.lower().str.strip()
        out = out.drop(columns=["regional_saude"], errors="ignore").merge(
            ref[["_mun_key", "regional_saude"]].drop_duplicates("_mun_key"),
            on="_mun_key",
            how="left",
        )
        out = out.drop(columns=["_mun_key"], errors="ignore")

    out["regional_saude"] = out["regional_saude"].fillna("Sem regional informada")
    return out


def _fmt_num(value: Any, digits: int = 1, suffix: str = "") -> str:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "indisponível"
        text = str(value).strip()
        if not text or text.lower() in {"nan", "none"}:
            return "indisponível"
        if isinstance(value, (int,)) or (isinstance(value, float) and float(value).is_integer()):
            return f"{int(value)}{suffix}"
        return f"{float(value):.{digits}f}{suffix}"
    except Exception:
        return "indisponível"


def _format_recs(nivel: str) -> list[str]:
    lines = []
    for eixo, rec in recommendations_for_stage(str(nivel or "verde").lower()):
        lines.append(_bullet("▶️", f"[{eixo}] {rec}"))
    return lines or [_bullet("▶️", "Manter monitoramento e validar fontes do ciclo.")]


def _epidemiology_block(indicadores: dict[str, Any] | None, resumo_mun: pd.DataFrame, ctx: dict[str, Any]) -> str:
    ind = indicadores or {}
    monitorados = ind.get("municipios_monitorados")
    if monitorados is None and not resumo_mun.empty and "municipio" in resumo_mun.columns:
        monitorados = resumo_mun["municipio"].nunique()
    laranja = ind.get("municipios_laranja_ou_mais", ctx.get("municipios_alerta"))

    top_lines: list[str] = []
    if not resumo_mun.empty and "score" in resumo_mun.columns:
        top = resumo_mun.sort_values("score", ascending=False).head(8)
        for _, row in top.iterrows():
            niv = row.get("nivel")
            top_lines.append(
                _bullet(
                    _nivel_icon(niv),
                    f"{row.get('municipio')}: {_nivel_label(niv)} | score {_fmt_num(row.get('score'), 0)} | "
                    f"🌡️ UTCI {_fmt_num(row.get('utci_proxy'))} | Tmax {_fmt_num(row.get('tmax'))}°C | "
                    f"🛏️ ocupação {_fmt_num(row.get('ocupacao_leitos_pct'))}%",
                )
            )
    if not top_lines:
        top_lines = [_bullet("•", "Ranking municipal indisponível neste ciclo.")]

    lines = [
        _section("INDICADORES CLIMA-SAÚDE / EPIDEMIOLÓGICOS", "📊"),
        _bullet("📍", f"Município sentinela: {ind.get('municipio', 'n/d')}"),
        _bullet("🚦", f"Nível/score sentinela: {_nivel_label(ind.get('nivel'))} / {_fmt_num(ind.get('score'), 0)}"),
        _bullet("📅", f"Data referência: {ind.get('data_referencia', ind.get('data', 'n/d'))}"),
        _bullet("🌡️", f"UTCI/proxy: {_fmt_num(ind.get('utci_proxy'))} | Heat index: {_fmt_num(ind.get('heat_index'))}"),
        _bullet(
            "☀️",
            f"Tmax: {_fmt_num(ind.get('tmax'), suffix='°C')} | Tmin: {_fmt_num(ind.get('tmin'), suffix='°C')} | "
            f"Umidade: {_fmt_num(ind.get('umidade_media'), suffix='%')}",
        ),
        _bullet(
            "🔥",
            f"Risco calor diário: {_fmt_num(ind.get('risco_calor_diario'))} | "
            f"Risco cumulativo 3d: {_fmt_num(ind.get('risco_cumulativo_3d'))}",
        ),
        _bullet(
            "📈",
            f"Onda de calor P95 (2d): {_fmt_num(ind.get('onda_calor_p95_2d'), 0)} | "
            f"Duração: {_fmt_num(ind.get('duracao_onda_calor_dias'), 0)} dia(s)",
        ),
        _bullet(
            "🫁",
            f"Casos SRAG (local): {_fmt_num(ind.get('casos_srag'), 0)} | "
            f"Positividade LACEN/GAL: {_fmt_num(ind.get('positividade_lacen_pct'), suffix='%')}",
        ),
        _bullet("📋", f"Notificações SINAN (DW): {_fmt_num(ind.get('notificacoes_sinan'), 0)}"),
        _bullet(
            "⚰️",
            f"Óbitos totais (SIM/DW): {_fmt_num(ind.get('obitos_total'), 0)} | "
            f"Suspeitos calor: {_fmt_num(ind.get('obitos_calor_suspeitos'), 0)}",
        ),
        _bullet("🛰️", f"Score sentinela: {_fmt_num(ind.get('score_sentinela'), 0)} | IQ ar: {_fmt_num(ind.get('iq_ar_score'))}"),
        _bullet(
            "🚑",
            f"Pressão assistencial: {_fmt_num(ind.get('pressao_calor_pct'), suffix='%')} | "
            f"Fonte: {ind.get('fonte_pressao', 'n/d')}",
        ),
        _bullet(
            "🏗️",
            f"Capacidade CNES (índice): {_fmt_num(ind.get('indice_capacidade_cnes'))} | "
            f"Estab.: {_fmt_num(ind.get('cnes_estabelecimentos_total'), 0)} | "
            f"Leitos CNES: {_fmt_num(ind.get('cnes_leitos_total'), 0)}",
        ),
        _bullet(
            "🛏️",
            f"Ocupação leitos (IndicaSUS): {_fmt_num(ind.get('ocupacao_leitos_pct'), suffix='%')} | "
            f"Leitos totais: {_fmt_num(ind.get('leitos_total'), 0)} | "
            f"Livres: {_fmt_num(ind.get('leitos_livres'), 0)}",
        ),
        _bullet("🔗", f"Fonte ocupação: {ind.get('fonte_ocupacao', 'n/d')}"),
        _bullet("🛡️", f"Índice resiliência: {_fmt_num(ind.get('indice_resiliencia'))}"),
        _bullet(
            "🏘️",
            f"Municípios monitorados: {_fmt_num(monitorados, 0)} | "
            f"Em alerta (laranja+): {_fmt_num(laranja, 0)}",
        ),
        "",
        _section("MUNICÍPIOS PRIORITÁRIOS (top score)", "🏅"),
        *top_lines,
    ]
    return "\n".join(lines)


def _ai_orientacoes(nivel: str, motivos: list[str], contexto: dict[str, Any], indicadores: dict[str, Any] | None) -> tuple[list[str], str]:
    """Retorna (bullets, fonte). Fonte: gemini | llm | deterministico."""
    # Fallback rico = próprio playbook (não só "acionar COE").
    base = [_bullet("▶️", f"[{eixo}] {acao}") for eixo, acao in recommendations_for_stage(str(nivel or "verde"))]

    use_ai = as_bool(env("USE_AI_ALERT_TEXT", "true"), True)
    if not use_ai:
        return base, "playbook_deterministico"

    ind = indicadores or {}
    prompt = (
        "Você é assessoria técnica sênior do CIEVS/SES-MT para ondas de calor.\n"
        "Gere um PLAYBOOK OPERACIONAL em até 10 bullets curtos e acionáveis.\n"
        "NÃO diga apenas 'acionar o COE'. Detalhe O QUE fazer em:\n"
        "1) Vigilância epidemiológica (SRAG/SIM/DARC/busca ativa)\n"
        "2) APS e território (idosos, rua, ILPI, hidratação)\n"
        "3) Urgência/hospital e regulação de leitos\n"
        "4) Logística de água/SRO/transporte por regionais críticas\n"
        "5) Comunicação de risco à população\n"
        "6) Saúde do trabalhador e pontos de resfriamento\n"
        "Use somente números presentes no JSON. Se um indicador estiver ausente/NaN, diga 'dado indisponível' e proponha como obter.\n"
        "Formato: cada linha começando com '- [Eixo] ação...' (sem emojis extras no meio da frase).\n\n"
        + json.dumps(
            {
                "nivel": nivel,
                "motivos": motivos[:10],
                "municipios_alerta": contexto.get("municipios_alerta"),
                "nivel_estadual": contexto.get("nivel_estadual"),
                "regionais_prioritarias": contexto.get("regionais_resumo"),
                "cuiaba": contexto.get("cuiaba_resumo"),
                "indicadores": {
                    k: ind.get(k)
                    for k in [
                        "municipio",
                        "utci_proxy",
                        "tmax",
                        "risco_cumulativo_3d",
                        "casos_srag",
                        "positividade_lacen_pct",
                        "notificacoes_sinan",
                        "obitos_total",
                        "obitos_calor_suspeitos",
                        "pressao_calor_pct",
                        "indice_capacidade_cnes",
                        "ocupacao_leitos_pct",
                        "leitos_livres",
                        "fonte_ocupacao",
                        "fonte_pressao",
                        "municipios_laranja_ou_mais",
                        "municipios_monitorados",
                        "iq_ar_score",
                        "score_sentinela",
                        "indice_resiliencia",
                    ]
                },
            },
            ensure_ascii=False,
            default=str,
        )
    )

    gemini_key = env("GEMINI_API_KEY")
    if gemini_key and not str(gemini_key).upper().startswith(("COLE_AQUI", "AI***")):
        preferred = env("GEMINI_MODEL", "gemini-2.5-flash") or "gemini-2.5-flash"
        # Modelos descontinuados são ignorados mesmo se ainda estiverem no .env.
        deprecated = {"gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-latest", "gemini-pro"}
        models = [preferred, "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-flash-latest", "gemini-2.5-pro"]
        models = [m for m in models if m and m not in deprecated]
        seen: set[str] = set()
        for model in models:
            if model in seen:
                continue
            seen.add(model)
            try:
                import requests

                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                r = requests.post(
                    url,
                    params={"key": gemini_key},
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                    timeout=60,
                    verify=_requests_verify(),
                )
                if r.status_code >= 400:
                    log.warning(
                        "Gemini modelo=%s status=%s body=%s",
                        model,
                        r.status_code,
                        _redact_secrets(r.text[:240]),
                    )
                    continue
                data = r.json()
                text = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text")
                )
                if text:
                    lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]
                    bullets = []
                    for ln in lines:
                        clean = ln.lstrip("•*-▶️ ").strip()
                        if not clean.startswith("["):
                            # mantém eixo se o modelo já trouxe
                            pass
                        bullets.append(_bullet("▶️", clean if clean.startswith("[") else clean))
                    if bullets:
                        log.info("Orientações IA geradas via Gemini (%s)", model)
                        return bullets[:10], f"gemini:{model}"
            except Exception as exc:
                log.warning("Falha Gemini (%s): %s", model, _redact_secrets(str(exc)))

    api_url = env("LLM_API_URL")
    api_key = env("LLM_API_KEY")
    if api_url and api_key and not str(api_key).upper().startswith("COLE_AQUI"):
        try:
            import requests

            payload = {
                "model": env("LLM_MODEL", "") or "",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            }
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            r = requests.post(api_url, headers=headers, json=payload, timeout=60, verify=_requests_verify())
            r.raise_for_status()
            data = r.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content") or data.get("text")
            if text:
                lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]
                bullets = []
                for ln in lines:
                    clean = ln.lstrip("•*-▶️ ").strip()
                    bullets.append(_bullet("▶️", clean))
                bullets = bullets[:10]
                log.info("Orientações IA geradas via LLM genérico")
                return bullets, "llm_generico"
        except Exception as exc:
            log.warning("Falha LLM genérico no alerta: %s", _redact_secrets(str(exc)))

    log.info("Usando playbook determinístico rico (Gemini/LLM indisponível)")
    return base, "playbook_deterministico"


def _clip(text: str, limit: int = 3900) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 60].rstrip() + "\n\n[...texto truncado para limite do canal]"


def _build_contexto(resumo_mun: pd.DataFrame, nivel: str, motivos: list[str]) -> dict[str, Any]:
    resumo_mun = _enrich_regional(resumo_mun)
    status, estado, regionais, _municipais, cuiaba = _build_status_alertas(resumo_mun)
    nivel_estadual = nivel
    municipios_alerta = 0
    if not estado.empty:
        nivel_estadual = str(estado.iloc[0].get("nivel_estadual") or nivel)
        municipios_alerta = int(estado.iloc[0].get("municipios_em_alerta") or 0)

    regionais_resumo = []
    if not regionais.empty:
        for _, row in regionais.sort_values("municipios_em_alerta", ascending=False).head(12).iterrows():
            regionais_resumo.append(
                f"{row.get('regional_saude')}: {int(row.get('municipios_em_alerta') or 0)} município(s)"
            )

    cuiaba_resumo = "Cuiabá sem município em alerta neste ciclo."
    if not cuiaba.empty:
        row = cuiaba.iloc[0]
        cuiaba_resumo = (
            f"Cuiabá em alerta — nível {row.get('nivel', 'n/d')} | "
            f"score {row.get('score', 'n/d')} | "
            f"motivo: {str(row.get('motivo', ''))[:180]}"
        )

    return {
        "status": status,
        "estado": estado,
        "regionais": regionais,
        "cuiaba": cuiaba,
        "nivel_estadual": nivel_estadual,
        "municipios_alerta": municipios_alerta,
        "regionais_resumo": regionais_resumo,
        "cuiaba_resumo": cuiaba_resumo,
        "motivos": motivos,
        "recs": _format_recs(nivel_estadual),
    }


def _score_of(row: dict[str, Any] | pd.Series) -> int:
    try:
        if "score" in row and pd.notna(row.get("score")):
            return int(float(row.get("score")))
    except Exception:
        pass
    return SCORE_BY_NIVEL.get(str(row.get("nivel", "")).strip().lower(), 0)


def _is_cuiaba(nome: str | None) -> bool:
    return str(nome or "").strip().lower() in {"cuiabá", "cuiaba"}


def _mun_block(row: pd.Series) -> str:
    return (
        f"{_nivel_icon(row.get('nivel'))} {row.get('municipio')}: {_nivel_label(row.get('nivel'))} | "
        f"score {_fmt_num(row.get('score'), 0)} | "
        f"🌡️ UTCI {_fmt_num(row.get('utci_proxy'))} | Tmax {_fmt_num(row.get('tmax'))}°C | "
        f"🛏️ ocupação {_fmt_num(row.get('ocupacao_leitos_pct'))}% | "
        f"🛡️ resiliência {_fmt_num(row.get('indice_resiliencia'))}"
    )


def _playbook_for_nivel(nivel: str) -> str:
    return "\n".join(_format_recs(nivel))


def _categorias_ativas() -> set[str]:
    raw = env("ALERT_VIGIA_CATEGORIAS", "estado,regional,municipal,cuiaba") or "estado,regional,municipal,cuiaba"
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def _min_score_municipais() -> int:
    # 0 = todos os municípios; 1 = amarela+; 2 = laranja+ (padrão operacional)
    try:
        return int(env("ALERT_VIGIA_MUNICIPIOS_MIN_SCORE", "0") or 0)
    except Exception:
        return 0


def _max_municipais() -> int:
    try:
        return max(1, int(env("ALERT_VIGIA_MAX_MUNICIPIOS", "160") or 160))
    except Exception:
        return 160


def _send_delay_seconds() -> float:
    try:
        return max(0.0, float(env("ALERT_VIGIA_SEND_DELAY_SECONDS", "0.35") or 0.35))
    except Exception:
        return 0.35


def compose_vigia_messages(
    data_referencia: str,
    nivel: str,
    motivos: list[str],
    resumo_mun: pd.DataFrame,
    old_nivel: str | None = None,
    force: bool = False,
    indicadores: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Monta o pacote VIGIA em 4 categorias com objetivos distintos.

    1) ESTADO — panorama completo para gestores SES/CIEVS
    2) REGIONAL — um alerta por ERS (16) com municípios da jurisdição
    3) MUNICIPAL — um alerta por município (exceto Cuiabá) com orientações locais
    4) CUIABÁ — alerta dedicado à capital
    """
    cats = _categorias_ativas()
    ctx = _build_contexto(resumo_mun, nivel, motivos)
    df = _enrich_regional(resumo_mun)
    ai_lines, ai_fonte = _ai_orientacoes(ctx["nivel_estadual"], motivos, ctx, indicadores)
    epi_txt = _epidemiology_block(indicadores, df, ctx)
    motivos_txt = "\n".join(_bullet("⚠️", m) for m in (motivos or [])[:10]) or _bullet("⚠️", "Sem motivos registrados")
    recs_txt = "\n".join(ctx["recs"])
    ai_txt = "\n".join(ai_lines)
    mudanca = (
        f"🔁 Nível anterior: {_nivel_label(old_nivel) if old_nivel else 'sem registro'} → atual: {_nivel_label(ctx['nivel_estadual'])}"
        if old_nivel != ctx["nivel_estadual"]
        else f"🚦 Nível atual: {_nivel_label(ctx['nivel_estadual'])}"
        + (" (envio forçado)" if force else "")
    )
    header = "🚨 VIGIA Clima-Saúde MT"
    messages: list[dict[str, str]] = []

    # ---- 1) ESTADO (SES / CIEVS) ----
    if "estado" in cats:
        reg_lines = ctx["regionais_resumo"] or ["Nenhuma regional com município em alerta (score ≥ 2)."]
        body_estado = (
            f"{header} | {TIPO_ICONS['estado']} {ALERT_TYPES['estado']}\n"
            f"🎯 Público-alvo: gestores SES/MT e CIEVS (panorama estadual completo)\n"
            f"📅 Data de referência: {data_referencia}\n"
            f"{mudanca}\n"
            f"🏘️ Municípios em alerta (laranja+): {ctx['municipios_alerta']}\n\n"
            f"{_section('PANORAMA DAS 16 ERS', '🏥')}\n"
            + "\n".join(_bullet("📍", x) for x in reg_lines)
            + "\n\n"
            f"{epi_txt}\n\n"
            f"{_section('GATILHOS / MOTIVOS ESTADUAIS', '⚡')}\n{motivos_txt}\n\n"
            f"{_section('PLAYBOOK ESTADUAL (além do COE)', '📘')}\n{recs_txt}\n\n"
            f"{_section(f'ORIENTAÇÕES IA / ASSESSORIA TÉCNICA (fonte: {ai_fonte})', '🤖')}\n{ai_txt}\n\n"
            f"📤 Encaminhamento SES/CIEVS: coordenar ERS prioritárias, regulação inter-regional, "
            f"comunicação estadual e revisão das fontes epi (SRAG/SINAN/SIM/GAL/CNES/IndicaSUS)."
        )
        messages.append({
            "tipo": "estado",
            "destino": "SES/CIEVS",
            "titulo_tipo": ALERT_TYPES["estado"],
            "subject": (
                f"{TIPO_ICONS['estado']} [VIGIA][{_nivel_label(ctx['nivel_estadual'])}] "
                f"{ALERT_TYPES['estado']} — {data_referencia}"
            ),
            "message": _clip(body_estado),
            "ai_fonte": ai_fonte,
        })

    # ---- 2) REGIONAL (um por ERS) ----
    if "regional" in cats and not df.empty and "regional_saude" in df.columns:
        regionais = (
            df["regional_saude"]
            .fillna("Sem regional informada")
            .astype(str)
            .replace({"": "Sem regional informada"})
        )
        for ers in sorted(regionais.unique()):
            if str(ers).strip().lower() in {"nan", "none"}:
                continue
            sub = df[df["regional_saude"].astype(str) == str(ers)].copy()
            if sub.empty:
                continue
            if "score" in sub.columns:
                sub = sub.sort_values("score", ascending=False)
            nivel_ers = str(sub.iloc[0].get("nivel") or ctx["nivel_estadual"])
            score_ers = _score_of(sub.iloc[0])
            n_alerta = int((sub["score"] >= 2).sum()) if "score" in sub.columns else 0
            mun_lines = [_bullet("•", _mun_block(r)) for _, r in sub.head(40).iterrows()]
            if len(sub) > 40:
                mun_lines.append(_bullet("•", f"... +{len(sub) - 40} município(s) nesta ERS"))
            playbook_ers = _playbook_for_nivel(nivel_ers)
            body_reg = (
                f"{header} | {TIPO_ICONS['regional']} {ALERT_TYPES['regional']}\n"
                f"🎯 Público-alvo: Escritório Regional de Saúde — {ers}\n"
                f"📅 Data de referência: {data_referencia}\n"
                f"🚦 Nível máximo na ERS: {_nivel_label(nivel_ers)} (score {_fmt_num(score_ers, 0)})\n"
                f"🗺️ Nível estadual de referência: {_nivel_label(ctx['nivel_estadual'])}\n"
                f"🏘️ Municípios da ERS: {len(sub)} | Em alerta (laranja+): {n_alerta}\n\n"
                f"{_section(f'MUNICÍPIOS SOB JURISDIÇÃO — {ers}', '📍')}\n"
                + "\n".join(mun_lines)
                + "\n\n"
                f"{_section('PLAYBOOK OPERACIONAL DA ERS', '📘')}\n{playbook_ers}\n\n"
                f"📤 Encaminhamento ERS: acionar municípios prioritários da lista, "
                f"pontos de resfriamento, busca ativa, regulação local e retorno ao CIEVS/SES."
            )
            messages.append({
                "tipo": "regional",
                "destino": str(ers),
                "titulo_tipo": f"{ALERT_TYPES['regional']} — {ers}",
                "subject": (
                    f"{TIPO_ICONS['regional']} [VIGIA][{_nivel_label(nivel_ers)}] "
                    f"ERS — {ers} — {data_referencia}"
                ),
                "message": _clip(body_reg),
                "ai_fonte": "playbook_regional",
            })

    # ---- 3) MUNICIPAL (um por município, exceto Cuiabá) ----
    if "municipal" in cats and not df.empty:
        min_score = _min_score_municipais()
        max_mun = _max_municipais()
        mun_df = df.copy()
        if "municipio" in mun_df.columns:
            mun_df = mun_df[~mun_df["municipio"].map(_is_cuiaba)]
        if "score" in mun_df.columns:
            mun_df = mun_df[pd.to_numeric(mun_df["score"], errors="coerce").fillna(0) >= min_score]
            mun_df = mun_df.sort_values("score", ascending=False)
        mun_df = mun_df.head(max_mun)
        for _, row in mun_df.iterrows():
            mun = str(row.get("municipio") or "Município")
            ers = str(row.get("regional_saude") or "Sem regional informada")
            niv = str(row.get("nivel") or "verde")
            motivo_local = str(row.get("motivo") or "Sem motivos registrados")
            motivos_loc = "\n".join(
                _bullet("⚠️", m.strip()) for m in motivo_local.split(";") if m.strip()
            ) or _bullet("⚠️", "Sem motivos registrados")
            playbook = _playbook_for_nivel(niv)
            ind_lines = [
                _bullet("🌡️", f"UTCI/proxy: {_fmt_num(row.get('utci_proxy'))} | Tmax: {_fmt_num(row.get('tmax'), suffix='°C')}"),
                _bullet("🔥", f"Risco cumulativo 3d: {_fmt_num(row.get('risco_cumulativo_3d'))}"),
                _bullet("🛏️", f"Ocupação leitos: {_fmt_num(row.get('ocupacao_leitos_pct'), suffix='%')} | Livres: {_fmt_num(row.get('leitos_livres'), 0)}"),
                _bullet("🚑", f"Pressão assistencial: {_fmt_num(row.get('pressao_calor_pct'), suffix='%')}"),
                _bullet("🛡️", f"Resiliência: {_fmt_num(row.get('indice_resiliencia'))} | CNES: {_fmt_num(row.get('indice_capacidade_cnes'))}"),
                _bullet(
                    "🫁",
                    f"SRAG: {_fmt_num(row.get('casos_srag'), 0)} | "
                    f"SINAN: {_fmt_num(row.get('notificacoes_sinan'), 0)} | "
                    f"Óbitos SIM: {_fmt_num(row.get('obitos_total'), 0)}",
                ),
            ]
            body_mun = (
                f"{header} | {TIPO_ICONS['municipal']} {ALERT_TYPES['municipal']}\n"
                f"🎯 Público-alvo: gestão municipal de saúde — {mun}\n"
                f"🏥 ERS de vinculação: {ers}\n"
                f"📅 Data de referência: {data_referencia}\n"
                f"🚦 Nível municipal: {_nivel_label(niv)} | score {_fmt_num(row.get('score'), 0)}\n"
                f"🗺️ Nível estadual de referência: {_nivel_label(ctx['nivel_estadual'])}\n\n"
                f"{_section('INDICADORES LOCAIS', '📊')}\n"
                + "\n".join(ind_lines)
                + "\n\n"
                f"{_section('GATILHOS / MOTIVOS LOCAIS', '⚡')}\n{motivos_loc}\n\n"
                f"{_section('ORIENTAÇÕES OPERACIONAIS DO MUNICÍPIO', '📘')}\n{playbook}\n\n"
                f"📤 Encaminhamento municipal: executar o playbook na rede local (APS/UPA/abrigos), "
                f"informar a {ers} e manter boletim diário enquanto o nível permanecer elevado."
            )
            messages.append({
                "tipo": "municipal",
                "destino": mun,
                "titulo_tipo": f"{ALERT_TYPES['municipal']} — {mun}",
                "subject": (
                    f"{TIPO_ICONS['municipal']} [VIGIA][{_nivel_label(niv)}] "
                    f"{mun} — {data_referencia}"
                ),
                "message": _clip(body_mun),
                "ai_fonte": "playbook_municipal",
            })

    # ---- 4) CUIABÁ (capital) ----
    if "cuiaba" in cats:
        cuiaba_rows = df[df["municipio"].map(_is_cuiaba)] if (not df.empty and "municipio" in df.columns) else pd.DataFrame()
        if not cuiaba_rows.empty:
            row = cuiaba_rows.sort_values("score", ascending=False).iloc[0] if "score" in cuiaba_rows.columns else cuiaba_rows.iloc[0]
            niv_c = str(row.get("nivel") or ctx["nivel_estadual"])
            motivo_c = str(row.get("motivo") or "")
            motivos_c = "\n".join(_bullet("⚠️", m.strip()) for m in motivo_c.split(";") if m.strip()) or motivos_txt
            sit = (
                f"{row.get('municipio')}: {_nivel_label(niv_c)} | score {_fmt_num(row.get('score'), 0)} | "
                f"UTCI {_fmt_num(row.get('utci_proxy'))} | Tmax {_fmt_num(row.get('tmax'))}°C | "
                f"ocupação {_fmt_num(row.get('ocupacao_leitos_pct'))}%"
            )
            playbook_c = _playbook_for_nivel(niv_c)
        else:
            niv_c = str(ctx["nivel_estadual"])
            sit = ctx["cuiaba_resumo"]
            motivos_c = motivos_txt
            playbook_c = recs_txt

        body_cuiaba = (
            f"{header} | {TIPO_ICONS['cuiaba']} {ALERT_TYPES['cuiaba']}\n"
            f"🎯 Público-alvo: gestão municipal de Cuiabá (capital) e ERS Cuiabá\n"
            f"📅 Data de referência: {data_referencia}\n"
            f"🚦 Nível Cuiabá: {_nivel_label(niv_c)}\n"
            f"🗺️ Nível estadual de referência: {_nivel_label(ctx['nivel_estadual'])}\n\n"
            f"{_section('SITUAÇÃO DE CUIABÁ', '🏙️')}\n{_bullet('📌', sit)}\n\n"
            f"{epi_txt}\n\n"
            f"{_section('GATILHOS / MOTIVOS', '⚡')}\n{motivos_c}\n\n"
            f"{_section('PLAYBOOK OPERACIONAL — CAPITAL', '📘')}\n{playbook_c}\n\n"
            f"{_section(f'ORIENTAÇÕES IA (fonte: {ai_fonte})', '🤖')}\n{ai_txt}\n\n"
            f"📤 Encaminhamento Cuiabá: reforçar APS/UPA, abrigos/resfriamento urbano, "
            f"população de rua/ILPI e monitoramento de ocupação hospitalar na capital."
        )
        messages.append({
            "tipo": "cuiaba",
            "destino": "Cuiabá",
            "titulo_tipo": ALERT_TYPES["cuiaba"],
            "subject": (
                f"{TIPO_ICONS['cuiaba']} [VIGIA][{_nivel_label(niv_c)}] "
                f"{ALERT_TYPES['cuiaba']} — {data_referencia}"
            ),
            "message": _clip(body_cuiaba),
            "ai_fonte": ai_fonte,
        })

    return messages


def dispatch_vigia_alerts(
    data_referencia: str,
    old: str | None,
    new: str,
    motivos: list[str],
    indicadores: dict,
    resumo_mun: pd.DataFrame | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Envia o pacote VIGIA (4 categorias) e registra auditoria."""
    df = resumo_mun if resumo_mun is not None else pd.DataFrame()
    messages = compose_vigia_messages(
        data_referencia=str(data_referencia),
        nivel=str(new),
        motivos=list(motivos or []),
        resumo_mun=df,
        old_nivel=old,
        force=force,
        indicadores=indicadores,
    )

    channel_any = {"email": False, "telegram": False, "webhook": False}
    per_type: dict[str, Any] = {}
    contagem = {"estado": 0, "regional": 0, "municipal": 0, "cuiaba": 0}

    log.info(
        "Preparando pacote VIGIA com %s alertas | categorias=%s | ai_fonte=%s | resumo_mun_linhas=%s",
        len(messages),
        sorted(_categorias_ativas()),
        messages[0].get("ai_fonte") if messages else "n/d",
        len(df),
    )

    for idx, item in enumerate(messages):
        tipo = item["tipo"]
        contagem[tipo] = contagem.get(tipo, 0) + 1
        key = f"{tipo}:{item.get('destino') or tipo}"
        results = dispatch_alert(
            item["subject"],
            item["message"],
            {
                "data_referencia": data_referencia,
                "nivel_anterior": old,
                "nivel_novo": new,
                "tipo_alerta_vigia": tipo,
                "destino": item.get("destino"),
                "titulo_tipo": item["titulo_tipo"],
                "indicadores": indicadores,
                "force": force,
                "ai_fonte": item.get("ai_fonte"),
            },
        )
        per_type[key] = results
        for k in channel_any:
            channel_any[k] = channel_any[k] or bool(results.get(k))

        with sqlite_conn() as conn:
            conn.execute(
                """INSERT INTO alertas_enviados
                   (created_at, nivel_anterior, nivel_novo, titulo, mensagem, canais, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    now_iso(),
                    old,
                    new,
                    item["subject"],
                    item["message"],
                    json.dumps(
                        {
                            "tipo": tipo,
                            "destino": item.get("destino"),
                            "ai_fonte": item.get("ai_fonte"),
                            **results,
                        },
                        ensure_ascii=False,
                    ),
                    "enviado" if any(results.values()) else "registrado_sem_canal",
                ),
            )
        delay = _send_delay_seconds()
        if delay and idx < len(messages) - 1:
            import time

            time.sleep(delay)

    log.info(
        "Alertas VIGIA enviados: contagem=%s | canais=%s | total=%s",
        contagem,
        channel_any,
        len(messages),
    )
    return {
        "tipos": per_type,
        "contagem": contagem,
        "canais": channel_any,
        "qtd": len(messages),
        "ai_fonte": next((m.get("ai_fonte") for m in messages if m.get("tipo") == "estado"), None),
    }
