# -*- coding: utf-8 -*-
"""
Alertas multinível do ARARAS MT.

Quatro escopos de disparo (com o mesmo núcleo de indicadores):
  1. estadual  → SES-MT / CIEVS estadual
  2. regional  → Regional de Saúde + municípios sob jurisdição
  3. municipal → Secretaria Municipal / plantão municipal
  4. cuiaba    → Vigidesastre Cuiabá (IBGE 5103403)

Cada payload traz: ícone/nível, indicadores climáticos e de saúde,
predição ~7d, e orientações para gestor, profissionais e população.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import pandas as pd

from sisclima.engines.stages import STAGE_ORDER

CUIABA_IBGE = "5103403"

EMOJI = {
    "verde": "🟢",
    "amarela": "🟡",
    "laranja": "🟠",
    "vermelha": "🔴",
    "roxa": "🟣",
    "cinza": "⚪",
}

LEVEL_LABEL = {
    "verde": "Verde — rotina",
    "amarela": "Amarela — atenção",
    "laranja": "Laranja — alerta",
    "vermelha": "Vermelha — resposta intensificada",
    "roxa": "Roxa — mobilização plena",
    "cinza": "Cinza — dados insuficientes",
}

ESCOPOS = ("estadual", "regional", "municipal", "cuiaba")

ORIENT = {
    "verde": {
        "gestor": (
            "Manter monitoramento de rotina; revisar estoques e planos locais; "
            "acompanhar boletins oficiais de tempo/desastres e o painel Clima-Saúde."
        ),
        "profissional": (
            "Reforçar hidratação e identificação precoce de desidratação e hipertermia; "
            "manter notificação de agravos sensíveis ao clima "
            "(síndrome respiratória grave, dengue e outras arboviroses, doenças diarreicas)."
        ),
        "populacao": (
            "Hidrate-se, evite exposição prolongada ao sol no pico de calor e "
            "elimine criadouros do mosquito."
        ),
    },
    "amarela": {
        "gestor": (
            "Ativar sala de situação municipal ou regional; emitir boletim diário; "
            "checar autonomia de insumos (soro de reidratação, soro, água) e comunicação de risco."
        ),
        "profissional": (
            "Priorizar idosos, gestantes, crianças e pessoas em situação de rua; "
            "orientar hidratação e resfriamento; intensificar busca ativa na atenção básica."
        ),
        "populacao": (
            "Evite atividades físicas no horário mais quente; use roupas leves; "
            "procure unidade básica ou pronto atendimento se houver tontura, confusão ou febre alta."
        ),
    },
    "laranja": {
        "gestor": (
            "Instalar centro de operações parcial; articular assistência, vigilância e comunicação; "
            "abrir pontos de resfriamento e hidratação; informar a Regional de Saúde e a Secretaria de Estado."
        ),
        "profissional": (
            "Expandir observação em ambiente climatizado; triagem por gravidade; "
            "reforçar investigação de dengue grave e síndrome respiratória aguda; fluxos de regulação."
        ),
        "populacao": (
            "Procure pontos de resfriamento e hidratação; não deixe crianças ou idosos "
            "sozinhos em ambientes quentes; siga orientações oficiais da secretaria municipal e estadual."
        ),
    },
    "vermelha": {
        "gestor": (
            "Centro de operações pleno; reuniões operacionais pelo menos duas vezes ao dia; "
            "priorizar leitos e regulação; comunicar risco à população e acionar contingência de energia e água."
        ),
        "profissional": (
            "Priorizar hipertermia, desidratação grave e descompensações "
            "cardiorrespiratórias; suspender eletivos se necessário; notificar oportunamente."
        ),
        "populacao": (
            "Situação de alto risco: evite exposição ao calor e à fumaça; "
            "procure atendimento imediato em sinais de gravidade; siga canais oficiais."
        ),
    },
    "roxa": {
        "gestor": (
            "Comando unificado e apoio entre entes federativos; redistribuição emergencial "
            "de insumos e leitos; comunicação de crise e registro para o pós-evento."
        ),
        "profissional": (
            "Protocolos de emergência plena; reforço de equipes; "
            "priorização absoluta de risco de vida e notificações imediatas."
        ),
        "populacao": (
            "Emergência sanitária climática: siga orientações oficiais da secretaria estadual e municipal; "
            "procure abrigo ou resfriamento e atendimento urgente se necessário."
        ),
    },
    "cinza": {
        "gestor": "Priorizar coleta e qualidade de dados antes de comunicar alerta definitivo.",
        "profissional": "Registrar lacunas de informação e manter vigilância clínica de rotina.",
        "populacao": "Acompanhe canais oficiais; mantenha cuidados gerais de hidratação e prevenção.",
    },
}

INDICADOR_COLS = [
    ("nivel", "Classificação operacional"),
    ("nivel_alerta_integrado", "Classificação integrada (clima + saúde + alertas oficiais)"),
    ("score", "Pontuação operacional (0 a 4)"),
    ("score_alerta_integrado", "Pontuação do alerta integrado"),
    ("tmax", "Temperatura máxima (°C)"),
    ("utci_proxy", "Sensação térmica estimada (°C)"),
    ("risco_cumulativo_3d", "Risco de calor acumulado em 3 dias"),
    ("ocupacao_leitos_pct", "Ocupação hospitalar IndicaSUS / SIEGES (%)"),
    ("kpi_sisreg_solicitacoes", "Pressão hospitalar SISREG (solicitações)"),
    ("kpi_sisreg_fila_h", "Fila média SISREG (horas)"),
    ("kpi_sisreg_semaforo", "Semáforo SISREG"),
    ("pressao_calor_pct", "Pressão por calor (painel 0–15)"),
    ("indice_pressao_saude", "Índice composto pressão saúde (0 a 100)"),
    ("semaforo_pressao", "Semáforo do índice composto"),
    ("pm25_ugm3", "Partículas finas no ar — PM2,5 (µg/m³)"),
    ("indice_saturacao_solo", "Índice de saturação do solo (0 a 100)"),
    ("classe_saturacao_solo", "Situação do solo"),
    ("incidencia_arbovirus_100k", "Incidência de arboviroses por 100 mil habitantes"),
    ("zscore_arbovirus", "Desvio epidêmico de arboviroses"),
    ("casos_srag", "Casos de síndrome respiratória aguda grave"),
    ("incidencia_srag_100k", "Incidência de síndrome respiratória grave por 100 mil"),
    ("letalidade_pct", "Letalidade (%)"),
    ("indice_tensao_climatica", "Índice de tensão climática (0 a 100)"),
    ("indice_carga_saude", "Índice de carga em saúde (0 a 100)"),
    ("indice_vigilancia_integrada", "Índice de vigilância integrada (0 a 100)"),
    ("tendencia_7d", "Tendência prevista para ~7 dias"),
    ("nivel_predicao_7d", "Classificação prevista para ~7 dias"),
    ("rit_0_100", "RIT — Risco Integrado Territorial (0 a 100)"),
    ("rit_faixa", "RIT — faixa (observado multidomínio)"),
    ("rit_dominio_dominante", "RIT — domínio dominante"),
    ("rit_completude_pct", "RIT — completude dos domínios (%)"),
    ("ehf_geocalor", "EHF GeoCalor (Fiocruz) — último dia"),
    ("intensidade_ehf", "Intensidade da onda EHF (baixa/severa/extrema)"),
    ("is_hw_day", "Dia de onda de calor GeoCalor (0/1)"),
    ("duracao_onda_ehf_dias", "Duração atual da onda EHF (dias)"),
    ("data_ehf_geocalor", "Data de referência do EHF GeoCalor"),
    ("componente_dominante", "Fator que mais elevou o alerta"),
    ("motivo", "Motivo principal"),
    ("motivo_integrado", "Motivo do alerta integrado"),
]


def _norm_nivel(x: Any) -> str:
    s = str(x or "").strip().lower()
    if s in {"amarelo"}:
        s = "amarela"
    if s in {"vermelho"}:
        s = "vermelha"
    if s in {"roxo"}:
        s = "roxa"
    return s if s in EMOJI else "cinza"


def _worst_nivel(series: pd.Series) -> str:
    if series is None or series.empty:
        return "cinza"
    ranks = series.map(lambda x: STAGE_ORDER.get(_norm_nivel(x), -1))
    if ranks.isna().all():
        return "cinza"
    best = int(ranks.max())
    for k, v in STAGE_ORDER.items():
        if v == best:
            return k
    return "cinza"


def _fmt(v: Any, nd: int = 1) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    try:
        f = float(v)
        if abs(f - int(f)) < 1e-9:
            return str(int(f))
        return f"{f:.{nd}f}".replace(".", ",")
    except Exception:
        s = str(v).strip()
        return s if s else "—"


def _motivo_em_linguagem_clara(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return "—"
    repl = [
        (r"(?i)\bSIS\s*est[aá]gio\s*", "Classificação operacional "),
        (r"(?i)\bUTCI/proxy\b", "sensação térmica estimada"),
        (r"(?i)\bUTCI\b", "sensação térmica estimada"),
        (r"(?i)\bRisco\s+cumulativo\s*3d\b", "risco de calor acumulado em 3 dias"),
        (r"(?i)\bINMET\b", "alerta oficial de tempo"),
        (r"(?i)\bCemaden\b", "alerta oficial de desastres"),
        (r"(?i)\bTITAN\b", "alertas oficiais integrados"),
        (r"(?i)\bSRAG\b", "síndrome respiratória grave"),
    ]
    out = s
    for pat, to in repl:
        out = re.sub(pat, to, out)
    out = re.sub(r"\s{2,}", " ", out).strip(" ;")
    if out and out[0].islower():
        out = out[0].upper() + out[1:]
    return out


def _pick_indicadores(row: pd.Series | dict) -> list[dict[str, str]]:
    data = row if isinstance(row, pd.Series) else pd.Series(row)
    out = []
    for col, label in INDICADOR_COLS:
        if col in data.index and pd.notna(data.get(col)):
            valor = _fmt(data.get(col))
            nota = ""
            if col == "ocupacao_leitos_pct" and "fonte_ocupacao" in data.index:
                fonte = str(data.get("fonte_ocupacao") or "")
                if "FALLBACK" in fonte.upper() or "ESTADUAL" in fonte.upper():
                    nota = " (estimado estadual — sem dado local)"
                elif "TEMPO_REAL" in fonte.upper():
                    nota = " (dado local em tempo real)"
            out.append({"campo": col, "rotulo": label, "valor": f"{valor}{nota}"})
    return out


def _orientacoes(nivel: str) -> dict[str, str]:
    return dict(ORIENT.get(_norm_nivel(nivel), ORIENT["cinza"]))


def _ensure_rit_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Garante EHF + IRM + RIT + compostos no frame (não altera nivel/pred 7d)."""
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()
    try:
        from sisclima.engines.resumo_frescor import refresh_resumo_multirisco

        return refresh_resumo_multirisco(df, inject_ehf=True, persist=False)
    except Exception:
        return df

def _geocalor_attach(payload: dict[str, Any], row: pd.Series | dict) -> None:
    """Anexa campos GeoCalor/EHF ao payload de alerta."""
    from sisclima.engines.ehf_geocalor import geocalor_linhas_alerta

    data = row if isinstance(row, dict) else row.to_dict()
    for key in (
        "ehf_geocalor",
        "ehf",
        "ehf_adaptado",
        "is_hw_day",
        "intensidade_ehf",
        "data_ehf_geocalor",
        "ehf_geocalor_idade_dias",
        "duracao_onda_ehf_dias",
        "duracao_onda_calor_dias",
        "ehf_fonte",
    ):
        if key in data and data.get(key) is not None:
            payload[key] = data.get(key)
    lines = geocalor_linhas_alerta(data)
    if lines:
        payload["geocalor_linhas"] = lines
    # resumo curto para Telegram estadual / ranking
    ehf = data.get("ehf_geocalor")
    if ehf is None or (isinstance(ehf, float) and pd.isna(ehf)):
        ehf = data.get("ehf")
    if ehf is not None and not (isinstance(ehf, float) and pd.isna(ehf)):
        try:
            payload["ehf_resumo"] = (
                f"EHF {float(ehf):.2f}"
                f" ({data.get('intensidade_ehf') or '—'}; ref. {data.get('data_ehf_geocalor') or '—'})"
            )
        except (TypeError, ValueError):
            pass


def _rit_from_row(row: pd.Series | dict) -> dict[str, Any]:
    """Contexto RIT municipal — produto paralelo à projeção térmica ~7d."""
    from sisclima.engines.rit_multirisco import DOMINIO_ROTULOS, scorecard_rit

    data = row if isinstance(row, pd.Series) else pd.Series(row)
    # Preferir scores já no resumo; senão recalcula
    if data.get("rit_0_100") is not None and not (
        isinstance(data.get("rit_0_100"), float) and pd.isna(data.get("rit_0_100"))
    ):
        rit_calc = {
            "rit_0_100": data.get("rit_0_100"),
            "rit_faixa": data.get("rit_faixa"),
            "rit_dominio_dominante": data.get("rit_dominio_dominante"),
            "rit_completude_pct": data.get("rit_completude_pct"),
            "rit_score_termico": data.get("rit_score_termico"),
            "rit_score_ar": data.get("rit_score_ar"),
            "rit_score_hidro": data.get("rit_score_hidro"),
            "rit_score_ehf": data.get("rit_score_ehf"),
            "rit_score_pressao": data.get("rit_score_pressao"),
            "rit_score_rede": data.get("rit_score_rede"),
            "rit_pressao_omitida_defasagem": data.get("rit_pressao_omitida_defasagem"),
        }
        sc = scorecard_rit(rit=rit_calc)
    else:
        sc = scorecard_rit(row=data)

    if not sc.get("disponivel"):
        return {
            "disponivel": False,
            "resumo": "RIT (Risco Integrado Territorial) indisponível nesta rodada.",
            "scorecard": sc,
            "dominios": sc.get("dominios") or [],
            "explicacao_dominante": sc.get("explicacao_dominante") or "—",
            "radar_compacto": sc.get("radar_compacto") or "—",
        }

    faixa = _norm_nivel(sc.get("rit_faixa"))
    if faixa == "cinza" and str(sc.get("rit_faixa") or "").strip():
        faixa = str(sc.get("rit_faixa")).strip().lower()
    dom = str(sc.get("dominio_dominante") or "—")
    rot_dom = DOMINIO_ROTULOS.get(dom, dom)
    omit = bool(sc.get("rit_pressao_omitida_defasagem"))
    nota_p = " Pressão omitida por defasagem." if omit else ""
    return {
        "disponivel": True,
        "rit_0_100": float(sc["rit_0_100"]),
        "rit_faixa": faixa,
        "icone_rit": EMOJI.get(faixa, "⚪") if faixa in EMOJI else "🧭",
        "rit_dominio_dominante": dom,
        "rit_dominio_dominante_rotulo": rot_dom,
        "rit_completude_pct": sc.get("rit_completude_pct"),
        "rit_pressao_omitida_defasagem": omit,
        "scorecard": sc,
        "dominios": sc.get("dominios") or [],
        "explicacao_dominante": sc.get("explicacao_dominante") or "—",
        "radar_compacto": sc.get("radar_compacto") or "—",
        "resumo": (
            f"RIT observado: {_fmt(sc['rit_0_100'], 0)}/100 ({LEVEL_LABEL.get(faixa, faixa)}); "
            f"principal influenciador: {rot_dom}. "
            f"{sc.get('explicacao_dominante') or ''} "
            f"Paralelo à projeção ~7d (térmica).{nota_p}"
        ).strip(),
    }


def _rit_from_df(df: pd.DataFrame) -> dict[str, Any]:
    """Contexto RIT agregado (estadual/regional) + influenciadores municipais."""
    from sisclima.engines.rit_multirisco import DOMINIO_ROTULOS

    if df is None or df.empty or "rit_0_100" not in df.columns:
        return {
            "disponivel": False,
            "resumo": "RIT (Risco Integrado Territorial) indisponível nesta rodada.",
            "dominantes_distribuicao": {},
            "municipios_rit_prioritarios": [],
        }
    work = df.copy()
    scores = pd.to_numeric(work["rit_0_100"], errors="coerce")
    if scores.notna().sum() == 0:
        return {
            "disponivel": False,
            "resumo": "RIT (Risco Integrado Territorial) indisponível nesta rodada.",
            "dominantes_distribuicao": {},
            "municipios_rit_prioritarios": [],
        }
    if "rit_faixa" in work.columns:
        faixa_pior = _worst_nivel(work["rit_faixa"])
        vc = work["rit_faixa"].map(lambda x: str(x or "").strip().lower()).value_counts()
        n_crit = int(work["rit_faixa"].astype(str).str.lower().isin(["vermelha", "roxa"]).sum())
    else:
        faixa_pior = "cinza"
        vc = pd.Series(dtype=int)
        n_crit = 0
    n = len(work)
    med = float(scores.median())
    mx = float(scores.max())
    omit = (
        int(work["rit_pressao_omitida_defasagem"].fillna(False).astype(bool).sum())
        if "rit_pressao_omitida_defasagem" in work.columns
        else 0
    )
    dominantes_distribuicao: dict[str, int] = {}
    if "rit_dominio_dominante" in work.columns:
        dvc = work["rit_dominio_dominante"].astype(str).value_counts()
        dominantes_distribuicao = {
            DOMINIO_ROTULOS.get(str(k), str(k)): int(v) for k, v in dvc.items() if str(k) not in {"", "nan", "—", "None"}
        }
    dom = next(iter(dominantes_distribuicao.keys()), "—")
    dist = ", ".join(f"{k}:{int(v)}" for k, v in vc.items()) if not vc.empty else "—"
    dist_dom = ", ".join(f"{k}:{v}" for k, v in dominantes_distribuicao.items()) if dominantes_distribuicao else "—"
    if omit == 1:
        nota_p = " Pressão omitida por defasagem em 1 município."
    elif omit > 1:
        nota_p = f" Pressão omitida por defasagem em {omit} municípios."
    else:
        nota_p = ""
    mun_rit = _top_rit_prioritarios(work, n=12)
    return {
        "disponivel": True,
        "rit_faixa_pior": faixa_pior,
        "icone_rit": EMOJI.get(faixa_pior, "🧭"),
        "rit_mediana": med,
        "rit_max": mx,
        "n_critico": n_crit,
        "n": n,
        "dominio_moda": dom,
        "dominantes_distribuicao": dominantes_distribuicao,
        "dominantes_distribuicao_txt": dist_dom,
        "distribuicao_faixas": dist,
        "n_pressao_omitida": omit,
        "municipios_rit_prioritarios": mun_rit,
        "resumo": (
            f"RIT observado: {n_crit}/{n} em faixa vermelha ou roxa; "
            f"mediana {_fmt(med, 0)} · máx {_fmt(mx, 0)}; "
            f"influenciadores mais frequentes: {dist_dom}. "
            f"Paralelo à projeção ~7d (térmica).{nota_p}"
        ),
    }


def _top_rit_prioritarios(base: pd.DataFrame, n: int = 12) -> list[dict[str, Any]]:
    """Top municípios por RIT com dominante e radar compacto."""
    from sisclima.engines.rit_multirisco import DOMINIO_ROTULOS

    if base is None or base.empty or "rit_0_100" not in base.columns:
        return []
    work = base.copy()
    work["_rit"] = pd.to_numeric(work["rit_0_100"], errors="coerce")
    top = work.dropna(subset=["_rit"]).sort_values("_rit", ascending=False).head(int(n))
    out: list[dict[str, Any]] = []
    for _, row in top.iterrows():
        rit_ctx = _rit_from_row(row)
        dom = str(rit_ctx.get("rit_dominio_dominante") or row.get("rit_dominio_dominante") or "—")
        out.append(
            {
                "municipio": str(row.get("municipio") or row.get("cod_ibge") or "—"),
                "cod_ibge": str(row.get("cod_ibge") or ""),
                "regional": str(row.get("regional_saude") or row.get("regional") or "—"),
                "nivel": _norm_nivel(row.get("_nivel") or row.get("nivel")),
                "rit_0_100": float(row["_rit"]),
                "rit_faixa": rit_ctx.get("rit_faixa") or row.get("rit_faixa"),
                "rit_dominio_dominante": dom,
                "rit_dominio_dominante_rotulo": DOMINIO_ROTULOS.get(dom, dom),
                "explicacao_dominante": rit_ctx.get("explicacao_dominante"),
                "radar_compacto": rit_ctx.get("radar_compacto") or "—",
                "dominios": rit_ctx.get("dominios") or [],
                "ehf_geocalor": row.get("ehf_geocalor"),
                "ehf": row.get("ehf"),
                "intensidade_ehf": row.get("intensidade_ehf"),
                "is_hw_day": row.get("is_hw_day"),
                "data_ehf_geocalor": row.get("data_ehf_geocalor"),
            }
        )
    return out


def _attach_rit(payload: dict[str, Any], rit: dict[str, Any]) -> dict[str, Any]:
    payload["rit"] = rit
    if rit.get("municipios_rit_prioritarios"):
        payload["municipios_rit_prioritarios"] = rit["municipios_rit_prioritarios"]
    return payload


def ensure_municipio_names(df: pd.DataFrame) -> pd.DataFrame:
    """Preenche municipio/regional ausentes a partir do catálogo IBGE/geo local."""
    if df is None or df.empty or "cod_ibge" not in df.columns:
        return df if df is not None else pd.DataFrame()
    out = df.copy()
    out["cod_ibge"] = out["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
    need_name = "municipio" not in out.columns or out["municipio"].isna().all() or (
        out["municipio"].astype(str).str.strip().isin(["", "nan", "None"]).mean() > 0.5
    )
    need_reg = "regional_saude" not in out.columns or out["regional_saude"].isna().all()
    if not need_name and not need_reg:
        return out
    try:
        from sisclima.ingestion.ibge_municipios import load_or_refresh_municipios

        cat = load_or_refresh_municipios()
        if cat is None or cat.empty:
            return out
        cat = cat.copy()
        cat["cod_ibge"] = cat["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
        cols = ["cod_ibge"]
        if need_name and "municipio" in cat.columns:
            cols.append("municipio")
        if need_reg and "regional_saude" in cat.columns:
            cols.append("regional_saude")
        if "populacao" in cat.columns and "populacao" not in out.columns:
            cols.append("populacao")
        cat = cat[cols].drop_duplicates("cod_ibge")
        out = out.drop(columns=[c for c in cols if c != "cod_ibge" and c in out.columns], errors="ignore")
        out = out.merge(cat, on="cod_ibge", how="left")
    except Exception:
        pass
    return out


def _coalesce_pred_cols(base: pd.DataFrame) -> pd.DataFrame:
    if base is None or base.empty:
        return base
    out = base.copy()
    candidates = [c for c in ["nivel_predicao_7d", "nivel_predicao_7d_x", "nivel_predicao_7d_y"] if c in out.columns]
    if not candidates:
        return out
    merged = out[candidates[0]]
    for c in candidates[1:]:
        better = out[c].where(~out[c].isna() & ~out[c].astype(str).str.lower().isin(["", "nan", "cinza", "none"]))
        merged = better.combine_first(merged)
    out["nivel_predicao_7d"] = merged
    drop = [c for c in candidates if c != "nivel_predicao_7d"]
    return out.drop(columns=drop, errors="ignore")


def _merge_base(
    resumo: pd.DataFrame,
    alerta_int: pd.DataFrame | None = None,
    pred: pd.DataFrame | None = None,
) -> pd.DataFrame:
    base = resumo.copy() if resumo is not None else pd.DataFrame()
    if base.empty:
        return base
    base = ensure_municipio_names(base)
    if "cod_ibge" in base.columns:
        base["cod_ibge"] = base["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
    if alerta_int is not None and not alerta_int.empty and "cod_ibge" in alerta_int.columns:
        ai = alerta_int.copy()
        ai["cod_ibge"] = ai["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
        # Preferir colunas do alerta integrado (mais recente na enriquecimento) sobre
        # valores eventualmente defasados já presentes no resumo.
        prefer = [
            c
            for c in [
                "nivel_alerta_integrado",
                "score_alerta_integrado",
                "componente_dominante",
                "motivo_integrado",
                "acao_recomendada",
                "data_processamento",
            ]
            if c in ai.columns
        ]
        drop_overlap = [c for c in prefer if c in base.columns]
        if drop_overlap:
            base = base.drop(columns=drop_overlap, errors="ignore")
        keep = [c for c in ai.columns if c == "cod_ibge" or c not in base.columns]
        base = base.merge(ai[keep], on="cod_ibge", how="left")
    if pred is not None and not pred.empty and "cod_ibge" in pred.columns:
        pr = pred.copy()
        pr["cod_ibge"] = pr["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
        want = [c for c in ["nivel_predicao_7d", "score_predicao", "horizonte_dias"] if c in pr.columns]
        if want:
            pr2 = pr[["cod_ibge"] + want].drop_duplicates("cod_ibge")
            overlapping = [c for c in want if c in base.columns]
            if overlapping:
                base = base.drop(columns=overlapping, errors="ignore")
            base = base.merge(pr2, on="cod_ibge", how="left")
    base = _coalesce_pred_cols(base)
    if "nivel_alerta_integrado" not in base.columns and "nivel" in base.columns:
        base["nivel_alerta_integrado"] = base["nivel"]
    if "nivel" not in base.columns and "nivel_alerta_integrado" in base.columns:
        base["nivel"] = base["nivel_alerta_integrado"]
    return base


def _data_referencia_escopo(df: pd.DataFrame) -> str | None:
    """Maior data de referência/processamento do escopo (não confundir com gerado_em)."""
    if df is None or df.empty:
        return None
    for col in (
        "data_processamento",
        "data_referencia",
        "atualizado_em",
        "data",
    ):
        if col not in df.columns:
            continue
        s = pd.to_datetime(df[col], errors="coerce")
        if s.notna().any():
            return pd.Timestamp(s.max()).strftime("%Y-%m-%d %H:%M")
    return None


def _titulo(escopo: str, nivel: str, alvo: str) -> str:
    icon = EMOJI.get(_norm_nivel(nivel), "⚪")
    lab = LEVEL_LABEL.get(_norm_nivel(nivel), nivel)
    prefix = {
        "estadual": "ALERTA ESTADUAL · SES-MT / CIEVS",
        "regional": f"ALERTA REGIONAL · {alvo}",
        "municipal": f"ALERTA MUNICIPAL · {alvo}",
        "cuiaba": "ALERTA VIGIDESASTRE CUIABÁ",
    }.get(escopo, "ALERTA SIS")
    return f"{icon} {prefix} · {lab}"


def _build_payload(
    *,
    escopo: str,
    nivel: str,
    alvo_nome: str,
    alvo_id: str,
    municipios: list[str],
    indicadores: list[dict[str, str]],
    predicao: dict[str, str],
    motivo: str,
    fontes: list[str],
    data_referencia: str | None = None,
) -> dict[str, Any]:
    niv = _norm_nivel(nivel)
    return {
        "escopo": escopo,
        "alvo_id": alvo_id,
        "alvo_nome": alvo_nome,
        "nivel": niv,
        "icone": EMOJI.get(niv, "⚪"),
        "nivel_rotulo": LEVEL_LABEL.get(niv, niv),
        "titulo": _titulo(escopo, niv, alvo_nome),
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "data_referencia": data_referencia or "—",
        "municipios_abrangidos": municipios,
        "n_municipios": len(municipios),
        "indicadores": indicadores,
        "predicao": predicao,
        "motivo": motivo or "—",
        "fontes": fontes,
        "orientacoes": _orientacoes(niv),
    }


def _predicao_from_rows(df: pd.DataFrame) -> dict[str, str]:
    if df is None or df.empty:
        return {"nivel_predicao_7d": "—", "resumo": "Predição de cerca de 7 dias indisponível nesta rodada."}
    work = _coalesce_pred_cols(df)
    if "nivel_predicao_7d" in work.columns:
        niv = _worst_nivel(work["nivel_predicao_7d"])
        vc = work["nivel_predicao_7d"].map(_norm_nivel).value_counts()
        moda = str(vc.index[0]) if not vc.empty else niv
    else:
        niv, moda = "cinza", "cinza"
    n_up = 0
    if "tendencia_7d" in work.columns:
        n_up = int(work["tendencia_7d"].astype(str).str.lower().isin(["subindo", "alta", "piora"]).sum())
    if niv == "cinza" and n_up > 0 and "nivel" in work.columns:
        niv = _worst_nivel(work["nivel"])
    return {
        "nivel_predicao_7d": niv,
        "icone_predicao": EMOJI.get(niv, "⚪"),
        "municipios_tendencia_alta": str(n_up),
        "resumo": (
            f"Mais grave prevista: {LEVEL_LABEL.get(niv, niv)}; "
            f"mais frequente: {LEVEL_LABEL.get(moda, moda)}. "
            f"Municípios com tendência de piora: {n_up}."
        ),
    }


def _ocupacao_agregada(df: pd.DataFrame, *, escopo: str = "estadual") -> tuple[float | None, str]:
    """Ocupação no escopo: ponderada por leitos; estadual pode cair no IndicaSUS estadual."""
    lo = pd.to_numeric(df.get("leitos_ocupados"), errors="coerce") if "leitos_ocupados" in df.columns else None
    lt = pd.to_numeric(df.get("leitos_total"), errors="coerce") if "leitos_total" in df.columns else None
    if lo is not None and lt is not None and float(lt.fillna(0).sum()) > 0:
        pct = 100.0 * float(lo.fillna(0).sum()) / float(lt.fillna(0).sum())
        return pct, "ponderada por leitos"
    if escopo == "estadual":
        try:
            from sisclima.core.db import read_table, table_exists

            if table_exists("hospital_ocupacao_estado"):
                est = read_table("hospital_ocupacao_estado")
                if est is not None and not est.empty and "ocupacao_pct" in est.columns:
                    return float(pd.to_numeric(est["ocupacao_pct"], errors="coerce").iloc[-1]), "IndicaSUS estadual"
        except Exception:
            pass
    if "ocupacao_leitos_pct" in df.columns:
        return float(pd.to_numeric(df["ocupacao_leitos_pct"], errors="coerce").mean()), "média municipal"
    return None, "sem dado"


def _ocupacao_estadual(df: pd.DataFrame) -> tuple[float | None, str]:
    """Compat: ocupa o agregador estadual."""
    return _ocupacao_agregada(df, escopo="estadual")


def _indicadores_agregados(df: pd.DataFrame, *, escopo: str = "estadual") -> list[dict[str, str]]:
    """Indicadores agregados com valor + escala (não usa município sentinela cru)."""
    if df.empty:
        return []
    pico = "estadual" if escopo == "estadual" else "da regional"
    limiar_dist = (
        "pior classificação define o alerta estadual"
        if escopo == "estadual"
        else "pior classificação define o alerta da regional"
    )
    inds: list[dict[str, str]] = []
    inds.append(
        {
            "campo": "n_municipios",
            "rotulo": "Municípios no escopo",
            "valor": str(len(df)),
            "escala": "contagem",
            "limiar": "",
        }
    )
    if "nivel_alerta_integrado" in df.columns or "nivel" in df.columns:
        col = "nivel_alerta_integrado" if "nivel_alerta_integrado" in df.columns else "nivel"
        vc = df[col].map(_norm_nivel).value_counts()
        dist = ", ".join(f"{k}:{int(v)}" for k, v in vc.items())
        inds.append(
            {
                "campo": "distribuicao_niveis",
                "rotulo": "Municípios por classificação",
                "valor": dist,
                "escala": "contagem por cor",
                "limiar": limiar_dist,
            }
        )

    if "score" in df.columns:
        score_max = pd.to_numeric(df["score"], errors="coerce").max()
        if pd.notna(score_max):
            inds.append(
                {
                    "campo": "score",
                    "rotulo": "Pontuação operacional (pior município)",
                    "valor": str(int(score_max)),
                    "escala": "0 a 4",
                    "limiar": "0 verde · 1 amarela · 2 laranja · 3 vermelha · 4 roxa",
                }
            )
    if "score_alerta_integrado" in df.columns:
        s2 = pd.to_numeric(df["score_alerta_integrado"], errors="coerce").max()
        if pd.notna(s2):
            inds.append(
                {
                    "campo": "score_alerta_integrado",
                    "rotulo": "Pontuação do alerta integrado (pior município)",
                    "valor": str(int(s2)),
                    "escala": "0 a 4",
                    "limiar": "máximo entre clima, saúde e alertas oficiais",
                }
            )

    for col, rotulo, escala, limiar, agg in [
        ("tmax", f"Temperatura máxima (pico {pico})", "°C", "atenção ≥37 · alerta ≥39 · intensificado ≥41 · pleno ≥43", "max"),
        (
            "utci_proxy",
            f"Sensação térmica estimada (pico {pico})",
            "°C (proxy)",
            "atenção >26 · alerta >32 · intensificado >38 · pleno >46",
            "max",
        ),
        (
            "risco_cumulativo_3d",
            "Risco de calor acumulado em 3 dias (pico)",
            "índice (típico 0–20+)",
            "atenção ≥3 · alerta ≥7 · intensificado ≥12 · pleno ≥18",
            "max",
        ),
        (
            "pressao_calor_pct",
            "Pressão assistencial por calor (pico)",
            "0 a 15 (proxy)",
            "atenção ≥2 · alerta ≥4 · intensificado ≥7 · pleno ≥10",
            "max",
        ),
        (
            "indice_pressao_saude",
            "Índice de pressão assistencial (pico)",
            "0 a 100",
            "verde ≤39 · amarela ≤69 · vermelha >69",
            "max",
        ),
        (
            "pm25_ugm3",
            "Partículas finas no ar — PM2,5 (pico)",
            "µg/m³",
            "referência OMS diária ~15 µg/m³",
            "max",
        ),
        (
            "incidencia_arbovirus_100k",
            "Incidência de arboviroses (pico) /100 mil",
            "casos / 100 mil",
            "interpretar com tendência",
            "max",
        ),
        (
            "casos_srag",
            "Casos de síndrome respiratória aguda grave (soma)",
            "casos",
            "acompanhar com incidência e ocupação",
            "sum",
        ),
    ]:
        if col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        if s.notna().sum() == 0:
            continue
        val = float(s.max()) if agg == "max" else float(s.fillna(0).sum())
        inds.append({"campo": col, "rotulo": rotulo, "valor": _fmt(val), "escala": escala, "limiar": limiar})

    ocup, ocup_fonte = _ocupacao_agregada(df, escopo=escopo)
    if ocup is not None:
        inds.append(
            {
                "campo": "ocupacao_leitos_pct",
                "rotulo": "Ocupação hospitalar IndicaSUS (média onde há leitos)",
                "valor": _fmt(ocup),
                "escala": "0 a 100 %",
                "limiar": f"atenção ≥75 · alerta ≥85 · fonte: {ocup_fonte} · ≠ pressão SISREG",
            }
        )
    if "fonte_ocupacao" in df.columns:
        n_rt = int(df["fonte_ocupacao"].astype(str).str.contains("TEMPO_REAL", case=False, na=False).sum())
        n_sem = int(df["fonte_ocupacao"].astype(str).str.contains("SEM_LEITOS", case=False, na=False).sum())
        inds.append(
            {
                "campo": "cobertura_ocupacao",
                "rotulo": "Cobertura ocupação IndicaSUS (hospital notificante)",
                "valor": f"{n_rt} de {len(df)} com leitos · {n_sem} sem hospital notificante",
                "escala": "municípios",
                "limiar": "ausência = sem unidade notificante (esperado); não inventar %",
            }
        )
    # Pressão hospitalar SISREG (demanda/regulação) — distinto da ocupação
    if "kpi_sisreg_solicitacoes" in df.columns:
        sols = pd.to_numeric(df["kpi_sisreg_solicitacoes"], errors="coerce")
        if sols.notna().any():
            inds.append(
                {
                    "campo": "kpi_sisreg_solicitacoes",
                    "rotulo": "Pressão hospitalar SISREG (solicitações — pico)",
                    "valor": _fmt(float(sols.max())),
                    "escala": "solicitações / fila",
                    "limiar": "demanda territorial · ≠ % ocupação de leitos",
                }
            )
    if "kpi_sisreg_disponivel" in df.columns or "kpi_sisreg_solicitacoes" in df.columns:
        if "kpi_sisreg_disponivel" in df.columns:
            n_sis = int(df["kpi_sisreg_disponivel"].fillna(False).astype(bool).sum())
        else:
            n_sis = int(pd.to_numeric(df["kpi_sisreg_solicitacoes"], errors="coerce").notna().sum())
        inds.append(
            {
                "campo": "cobertura_sisreg",
                "rotulo": "Cobertura pressão SISREG (regulação)",
                "valor": f"{n_sis} de {len(df)} municípios",
                "escala": "municípios com sinal de fila/solicitação",
                "limiar": "aplica-se com ou sem hospital próprio",
            }
        )
    if "semaforo_pressao" in df.columns:
        vc = df["semaforo_pressao"].astype(str).str.lower().str.strip().value_counts()
        if not vc.empty:
            dist = ", ".join(f"{k}:{int(v)}" for k, v in vc.items())
            inds.append(
                {
                    "campo": "distribuicao_semaforo_pressao",
                    "rotulo": "Municípios por semáforo de pressão assistencial",
                    "valor": dist,
                    "escala": "verde / amarela / vermelha",
                    "limiar": "composto (ocupação se houver + SISREG + SINAN + SIM) ≠ nível Verde→Roxa",
                }
            )
    # RIT — Risco Integrado Territorial (observado; não substitui projeção ~7d)
    if "rit_faixa" in df.columns or "rit_0_100" in df.columns:
        rit = _rit_from_df(df)
        if rit.get("disponivel"):
            inds.append(
                {
                    "campo": "rit_n_critico",
                    "rotulo": "RIT — municípios em faixa vermelha ou roxa",
                    "valor": f"{rit.get('n_critico')}/{rit.get('n')}",
                    "escala": "contagem (observado multidomínio)",
                    "limiar": "paralelo à projeção ~7d térmica · max entre domínios válidos",
                }
            )
            inds.append(
                {
                    "campo": "rit_0_100",
                    "rotulo": "RIT — mediana / máximo (0 a 100)",
                    "valor": f"{_fmt(rit.get('rit_mediana'), 0)} / {_fmt(rit.get('rit_max'), 0)}",
                    "escala": "0 a 100",
                    "limiar": "0–24 verde · 25–49 amarela · 50–69 laranja · 70–84 vermelha · 85–100 roxa",
                }
            )
            if rit.get("distribuicao_faixas") and rit.get("distribuicao_faixas") != "—":
                inds.append(
                    {
                        "campo": "rit_distribuicao_faixas",
                        "rotulo": "RIT — municípios por faixa",
                        "valor": str(rit.get("distribuicao_faixas")),
                        "escala": "contagem por faixa",
                        "limiar": f"domínio mais frequente: {rit.get('dominio_moda') or '—'}",
                    }
                )
            if int(rit.get("n_pressao_omitida") or 0) > 0:
                inds.append(
                    {
                        "campo": "rit_pressao_omitida",
                        "rotulo": "RIT — pressão omitida por defasagem",
                        "valor": str(rit.get("n_pressao_omitida")),
                        "escala": "municípios",
                        "limiar": "não eleva o RIT quando carga >14 dias",
                    }
                )
    # GeoCalor / EHF no recorte (estadual ou regional)
    if "ehf_geocalor" in df.columns or "ehf" in df.columns:
        ehf_s = pd.to_numeric(df.get("ehf_geocalor", df.get("ehf")), errors="coerce")
        n_pos = int((ehf_s.fillna(0) > 0).sum())
        n_hw = (
            int(pd.to_numeric(df["is_hw_day"], errors="coerce").fillna(0).gt(0).sum())
            if "is_hw_day" in df.columns
            else 0
        )
        n_onda = (
            int(pd.to_numeric(df["onda_geocalor_ativa"], errors="coerce").fillna(0).gt(0).sum())
            if "onda_geocalor_ativa" in df.columns
            else n_hw
        )
        data_ref = None
        idade = None
        if "data_ehf_geocalor" in df.columns and df["data_ehf_geocalor"].notna().any():
            data_ref = str(df["data_ehf_geocalor"].dropna().astype(str).mode().iloc[0])
        if "ehf_geocalor_idade_dias" in df.columns and df["ehf_geocalor_idade_dias"].notna().any():
            idade = int(pd.to_numeric(df["ehf_geocalor_idade_dias"], errors="coerce").dropna().mode().iloc[0])
        inds.append(
            {
                "campo": "ehf_geocalor_cobertura",
                "rotulo": "GeoCalor / EHF — municípios com EHF > 0",
                "valor": f"{n_pos}/{len(df)}" + (f" · onda ativa {n_onda}" if n_onda else ""),
                "escala": "contagem",
                "limiar": f"ref. {data_ref or '—'} · Nairn & Fawcett / Fiocruz",
            }
        )
        if data_ref is not None or idade is not None:
            inds.append(
                {
                    "campo": "ehf_geocalor_frescor",
                    "rotulo": "GeoCalor STAR — data / idade",
                    "valor": str(data_ref or "—"),
                    "escala": "data",
                    "limiar": f"defasagem {idade}d" if idade is not None else "idade n/d",
                }
            )
        if "onda_geocalor_ativa" in df.columns:
            inds.append(
                {
                    "campo": "onda_geocalor_ativa",
                    "rotulo": "Onda GeoCalor ativa (is_hw_day + EHF>0)",
                    "valor": f"{n_onda}/{len(df)}",
                    "escala": "contagem",
                    "limiar": "indicador composto — não substitui o nível ARARAS",
                }
            )
        if ehf_s.notna().any():
            inds.append(
                {
                    "campo": "ehf_geocalor_max",
                    "rotulo": "GeoCalor / EHF — máximo no recorte",
                    "valor": float(ehf_s.max()),
                    "escala": "índice EHF",
                    "limiar": ">0 sinal de excesso de calor; intensidade baixa/severa/extrema",
                }
            )
    # Compostos / vigilância
    if "sinal_fumaca_sem_pm" in df.columns:
        n_fum = int(pd.to_numeric(df["sinal_fumaca_sem_pm"], errors="coerce").fillna(0).sum())
        inds.append(
            {
                "campo": "sinal_fumaca_sem_pm",
                "rotulo": "Fumaça sem PM2,5 (focos>0 e PM nulo)",
                "valor": f"{n_fum}/{len(df)}",
                "escala": "contagem",
                "limiar": "não interpretar como ar limpo",
            }
        )
    if "completude_sala_pct" in df.columns:
        med = pd.to_numeric(df["completude_sala_pct"], errors="coerce").median()
        if pd.notna(med):
            inds.append(
                {
                    "campo": "completude_sala_pct",
                    "rotulo": "Completude Sala (fontes críticas)",
                    "valor": float(med),
                    "escala": "%",
                    "limiar": "meta operacional ≥60%",
                }
            )
    if "sisagua_monitoramento_valido" in df.columns:
        ok = int(pd.to_numeric(df["sisagua_monitoramento_valido"], errors="coerce").fillna(0).gt(0).sum())
        inds.append(
            {
                "campo": "sisagua_cobertura",
                "rotulo": "SISAGUA — municípios com monitoramento válido",
                "valor": f"{ok}/{len(df)}",
                "escala": "contagem",
                "limiar": "Visa / água segura",
            }
        )
    if "entomologia_iip" in df.columns:
        alto = int(pd.to_numeric(df["entomologia_iip"], errors="coerce").fillna(0).gt(3.9).sum())
        inds.append(
            {
                "campo": "entomologia_alerta",
                "rotulo": "Entomologia — municípios com IIP > 3,9",
                "valor": f"{alto}/{len(df)}",
                "escala": "contagem",
                "limiar": "LIRAa / risco vetorial",
            }
        )
    if "denuncias_sla_pct" in df.columns or "denuncias_sla_ok" in df.columns:
        if "denuncias_sla_pct" in df.columns:
            med = pd.to_numeric(df["denuncias_sla_pct"], errors="coerce").median()
            val = f"{float(med):.0f}%" if pd.notna(med) else "—"
        else:
            ok = int(pd.to_numeric(df["denuncias_sla_ok"], errors="coerce").fillna(0).eq(1).sum())
            val = f"{ok}/{len(df)} OK"
        inds.append(
            {
                "campo": "denuncias_sla",
                "rotulo": "Denúncias ambientais — SLA",
                "valor": val,
                "escala": "% ou contagem",
                "limiar": "Visa / COVSAN",
            }
        )
    return inds


def _motivo_agregado(df: pd.DataFrame) -> str:
    for col in ["motivo_integrado", "motivo", "orientacao_leiga"]:
        if col in df.columns:
            s = df[col].dropna().astype(str)
            s = s[~s.str.lower().isin(["", "nan", "none", "—"])]
            if not s.empty:
                return _motivo_em_linguagem_clara(str(s.iloc[0])[:500])
    return "Consolidado a partir da classificação operacional e dos componentes climáticos e assistenciais."


def _top_prioritarios(base: pd.DataFrame, n: int = 8) -> list[dict[str, Any]]:
    sort_cols = ["_rank"] + ([c for c in ["score", "risco_cumulativo_3d"] if c in base.columns])
    top = base.sort_values(sort_cols, ascending=False).head(n)
    out = []
    for _, row in top.iterrows():
        out.append(
            {
                "municipio": str(row.get("municipio") or row.get("cod_ibge") or "—"),
                "cod_ibge": str(row.get("cod_ibge") or ""),
                "regional": str(row.get("regional_saude") or "—"),
                "nivel": _norm_nivel(row.get("_nivel") or row.get("nivel")),
                "score": row.get("score"),
                "tmax": row.get("tmax"),
                "utci_proxy": row.get("utci_proxy"),
                "risco_cumulativo_3d": row.get("risco_cumulativo_3d"),
                "ocupacao_leitos_pct": row.get("ocupacao_leitos_pct"),
                "indice_pressao_saude": row.get("indice_pressao_saude"),
                "semaforo_pressao": row.get("semaforo_pressao"),
                "fonte_ocupacao": row.get("fonte_ocupacao"),
                "kpi_sisreg_solicitacoes": row.get("kpi_sisreg_solicitacoes"),
                "kpi_sisreg_semaforo": row.get("kpi_sisreg_semaforo"),
                "n_aldeias": row.get("n_aldeias"),
                "n_quilombos": row.get("n_quilombos"),
                "n_assentamentos": row.get("n_assentamentos"),
                "n_barragens_dpa_alto": row.get("n_barragens_dpa_alto"),
                "cenario_dominante": row.get("cenario_dominante"),
                "rit_0_100": row.get("rit_0_100"),
                "rit_faixa": row.get("rit_faixa"),
                "rit_dominio_dominante": row.get("rit_dominio_dominante"),
                "ehf_geocalor": row.get("ehf_geocalor"),
                "ehf": row.get("ehf"),
                "intensidade_ehf": row.get("intensidade_ehf"),
                "is_hw_day": row.get("is_hw_day"),
                "data_ehf_geocalor": row.get("data_ehf_geocalor"),
                "indicadores": _pick_indicadores(row),
            }
        )
        # Anexa radar RIT ao prioritário operacional (sem reordenar a lista)
        try:
            rit_ctx = _rit_from_row(row)
            out[-1]["explicacao_dominante"] = rit_ctx.get("explicacao_dominante")
            out[-1]["radar_compacto"] = rit_ctx.get("radar_compacto")
            out[-1]["rit_dominio_dominante_rotulo"] = rit_ctx.get("rit_dominio_dominante_rotulo")
        except Exception:
            pass
    return out


def _ibge_tokens(value: Any) -> set[str]:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) < 6:
        return set()
    out = {digits[:6]}
    if len(digits) >= 7:
        out.add(digits[:7])
    return out


def _force_municipio_ids() -> set[str]:
    from sisclima.core.config import env

    raw = env("ALERT_FORCE_MUNICIPIOS", "") or ""
    out: set[str] = set()
    for part in raw.replace(";", ",").split(","):
        out |= _ibge_tokens(part)
    return out


def build_alertas_multinivel(
    resumo: pd.DataFrame,
    alerta_integrado: pd.DataFrame | None = None,
    predicao_7d: pd.DataFrame | None = None,
    min_level: str = "amarela",
) -> list[dict[str, Any]]:
    """Gera lista de payloads: 1 estadual + N regionais + N municipais (≥min) + Cuiabá."""
    from sisclima.core.config import env

    base = _merge_base(resumo, alerta_integrado, predicao_7d)
    if base.empty:
        return []
    base = _ensure_rit_cols(base)

    min_rank = STAGE_ORDER.get(_norm_nivel(min_level), 1)
    nivel_col = "nivel_alerta_integrado" if "nivel_alerta_integrado" in base.columns else "nivel"
    base["_nivel"] = base[nivel_col].map(_norm_nivel) if nivel_col in base.columns else "cinza"
    base["_rank"] = base["_nivel"].map(STAGE_ORDER).fillna(-1)

    fontes = [
        "Open-Meteo",
        "INMET",
        "Cemaden",
        "ANA",
        "Copernicus/CAMS (quando disponível)",
        "SINAN/SIVEP/SIM/IndicaSUS (DW)",
        "SISREG (regulação/fila)",
        "Vigibarragens (FUNAI/Palmares/INCRA/SNISB)",
        "ARARAS MT",
        "RIT multirisco (observado)",
        "GeoCalor / EHF (Fiocruz–LAGAS)",
    ]

    payloads: list[dict[str, Any]] = []

    # 1) Estadual → SES
    niv_est = _worst_nivel(base["_nivel"])
    mun_names = base.get("municipio", pd.Series(dtype=str)).dropna().astype(str)
    mun_names = mun_names[~mun_names.str.lower().isin(["", "nan", "none"])]
    top_n = int(env("ALERT_SES_TOP_MUNICIPIOS", "8") or 8)
    est = _build_payload(
        escopo="estadual",
        nivel=niv_est,
        alvo_nome="Estado de Mato Grosso · Secretaria de Estado da Saúde / CIEVS",
        alvo_id="MT",
        municipios=sorted(mun_names.unique().tolist()),
        indicadores=_indicadores_agregados(base, escopo="estadual"),
        predicao=_predicao_from_rows(base),
        motivo=_motivo_agregado(base.sort_values("_rank", ascending=False)),
        fontes=fontes,
        data_referencia=_data_referencia_escopo(base),
    )
    est["municipios_prioritarios"] = _top_prioritarios(base, n=top_n)
    if "nivel" in base.columns:
        est["distribuicao"] = base["nivel"].map(_norm_nivel).value_counts().to_dict()
    else:
        est["distribuicao"] = base["_nivel"].value_counts().to_dict()
    _attach_rit(est, _rit_from_df(base))
    payloads.append(est)

    # 2) Regionais
    if "regional_saude" in base.columns:
        top_reg = int(env("ALERT_REGIONAL_TOP_MUNICIPIOS", "8") or 8)
        for reg, g in base.groupby(base["regional_saude"].fillna("Sem regional").astype(str)):
            niv = _worst_nivel(g["_nivel"])
            g_names = g.get("municipio", pd.Series(dtype=str)).dropna().astype(str)
            g_names = g_names[~g_names.str.lower().isin(["", "nan", "none"])]
            rp = _build_payload(
                escopo="regional",
                nivel=niv,
                alvo_nome=str(reg),
                alvo_id=str(reg),
                municipios=sorted(g_names.unique().tolist()),
                indicadores=_indicadores_agregados(g, escopo="regional"),
                predicao=_predicao_from_rows(g),
                motivo=_motivo_agregado(g.sort_values("_rank", ascending=False)),
                fontes=fontes,
                data_referencia=_data_referencia_escopo(g),
            )
            rp["municipios_prioritarios"] = _top_prioritarios(g, n=top_reg)
            rp["distribuicao"] = g["_nivel"].value_counts().to_dict()
            _attach_rit(rp, _rit_from_df(g))
            payloads.append(rp)

    # 3) Municipais
    crit = base[base["_rank"] >= min_rank].copy()
    force_ids = _force_municipio_ids()
    if force_ids and "cod_ibge" in base.columns:
        extra_mask = base["cod_ibge"].map(lambda x: bool(_ibge_tokens(x) & force_ids))
        extra = base[extra_mask]
        if not extra.empty:
            key = "cod_ibge" if "cod_ibge" in crit.columns else None
            crit = pd.concat([crit, extra], ignore_index=True)
            if key:
                crit = crit.drop_duplicates(key, keep="first")
    for _, row in crit.iterrows():
        mun = str(row.get("municipio") or row.get("cod_ibge") or "Município")
        mp = _build_payload(
            escopo="municipal",
            nivel=row.get("_nivel"),
            alvo_nome=mun,
            alvo_id=str(row.get("cod_ibge") or mun),
            municipios=[mun],
            indicadores=_pick_indicadores(row),
            predicao={
                "nivel_predicao_7d": _norm_nivel(row.get("nivel_predicao_7d")),
                "icone_predicao": EMOJI.get(_norm_nivel(row.get("nivel_predicao_7d")), "⚪"),
                "resumo": (
                    f"Predição em cerca de 7 dias: "
                    f"{LEVEL_LABEL.get(_norm_nivel(row.get('nivel_predicao_7d')), '—')}"
                ),
            },
            motivo=_motivo_em_linguagem_clara(str(row.get("motivo_integrado") or row.get("motivo") or "—")),
            fontes=fontes,
            data_referencia=_data_referencia_escopo(pd.DataFrame([row])),
        )
        mp["regional"] = str(row.get("regional_saude") or "—")
        mp["score"] = row.get("score")
        mp["tmax"] = row.get("tmax")
        mp["utci_proxy"] = row.get("utci_proxy")
        mp["risco_cumulativo_3d"] = row.get("risco_cumulativo_3d")
        mp["ocupacao_leitos_pct"] = row.get("ocupacao_leitos_pct")
        mp["fonte_ocupacao"] = row.get("fonte_ocupacao")
        mp["leitos_total"] = row.get("leitos_total")
        mp["leitos_ocupados"] = row.get("leitos_ocupados")
        mp["kpi_sisreg_solicitacoes"] = row.get("kpi_sisreg_solicitacoes")
        mp["kpi_sisreg_fila_h"] = row.get("kpi_sisreg_fila_h")
        mp["kpi_sisreg_semaforo"] = row.get("kpi_sisreg_semaforo")
        mp["kpi_sisreg_score"] = row.get("kpi_sisreg_score")
        mp["pressao_calor_pct"] = row.get("pressao_calor_pct")
        mp["indice_pressao_saude"] = row.get("indice_pressao_saude")
        mp["semaforo_pressao"] = row.get("semaforo_pressao")
        mp["pm25_ugm3"] = row.get("pm25_ugm3")
        mp["iq_ar_score"] = row.get("iq_ar_score")
        mp["qualidade_ar_nivel"] = row.get("qualidade_ar_nivel")
        mp["situacao_hidro"] = row.get("situacao_hidro")
        mp["nivel_alerta_hidro"] = row.get("nivel_alerta_hidro")
        mp["casos_srag"] = row.get("casos_srag")
        mp["casos_arbovirus_7d"] = row.get("casos_arbovirus_7d")
        mp["n_aldeias"] = row.get("n_aldeias")
        mp["n_quilombos"] = row.get("n_quilombos")
        mp["n_assentamentos"] = row.get("n_assentamentos")
        mp["n_terras_indigenas"] = row.get("n_terras_indigenas")
        mp["familias_assentamentos"] = row.get("familias_assentamentos")
        mp["n_barragens_dpa_alto"] = row.get("n_barragens_dpa_alto")
        mp["n_territorios_tradicionais"] = row.get("n_territorios_tradicionais")
        mp["cenario_dominante"] = row.get("cenario_dominante")
        mp["cuidados_territoriais"] = row.get("cuidados_territoriais")
        mp["rit_0_100"] = row.get("rit_0_100")
        mp["rit_faixa"] = row.get("rit_faixa")
        mp["rit_dominio_dominante"] = row.get("rit_dominio_dominante")
        mp["rit_completude_pct"] = row.get("rit_completude_pct")
        _attach_rit(mp, _rit_from_row(row))
        _geocalor_attach(mp, row)
        payloads.append(mp)

    # 4) Cuiabá
    cui = base[base["cod_ibge"].astype(str) == CUIABA_IBGE] if "cod_ibge" in base.columns else pd.DataFrame()
    if cui.empty and "municipio" in base.columns:
        cui = base[base["municipio"].astype(str).str.lower().str.contains("cuiab", na=False)]
    if not cui.empty:
        row = cui.sort_values("_rank", ascending=False).iloc[0]
        cp = _build_payload(
            escopo="cuiaba",
            nivel=row.get("_nivel"),
            alvo_nome="Cuiabá",
            alvo_id=CUIABA_IBGE,
            municipios=["Cuiabá"],
            indicadores=_pick_indicadores(row),
            predicao={
                "nivel_predicao_7d": _norm_nivel(row.get("nivel_predicao_7d")),
                "icone_predicao": EMOJI.get(_norm_nivel(row.get("nivel_predicao_7d")), "⚪"),
                "resumo": (
                    f"Predição em cerca de 7 dias: "
                    f"{LEVEL_LABEL.get(_norm_nivel(row.get('nivel_predicao_7d')), '—')}"
                ),
            },
            motivo=_motivo_em_linguagem_clara(
                str(row.get("motivo_integrado") or row.get("motivo") or "Alerta dedicado Vigidesastre Cuiabá.")
            ),
            fontes=fontes + ["Vigidesastre Cuiabá"],
            data_referencia=_data_referencia_escopo(pd.DataFrame([row])),
        )
        cp["remetente"] = "VIGIDESASTRE CUIABÁ"
        cp["regional"] = str(row.get("regional_saude") or "Cuiabá")
        cp["score"] = row.get("score")
        cp["tmax"] = row.get("tmax")
        cp["utci_proxy"] = row.get("utci_proxy")
        cp["risco_cumulativo_3d"] = row.get("risco_cumulativo_3d")
        cp["ocupacao_leitos_pct"] = row.get("ocupacao_leitos_pct")
        cp["fonte_ocupacao"] = row.get("fonte_ocupacao")
        cp["leitos_total"] = row.get("leitos_total")
        cp["leitos_ocupados"] = row.get("leitos_ocupados")
        cp["kpi_sisreg_solicitacoes"] = row.get("kpi_sisreg_solicitacoes")
        cp["kpi_sisreg_fila_h"] = row.get("kpi_sisreg_fila_h")
        cp["kpi_sisreg_semaforo"] = row.get("kpi_sisreg_semaforo")
        cp["kpi_sisreg_score"] = row.get("kpi_sisreg_score")
        cp["pressao_calor_pct"] = row.get("pressao_calor_pct")
        cp["indice_pressao_saude"] = row.get("indice_pressao_saude")
        cp["semaforo_pressao"] = row.get("semaforo_pressao")
        cp["pm25_ugm3"] = row.get("pm25_ugm3")
        cp["iq_ar_score"] = row.get("iq_ar_score")
        cp["qualidade_ar_nivel"] = row.get("qualidade_ar_nivel")
        cp["situacao_hidro"] = row.get("situacao_hidro")
        cp["nivel_alerta_hidro"] = row.get("nivel_alerta_hidro")
        cp["n_aldeias"] = row.get("n_aldeias")
        cp["n_quilombos"] = row.get("n_quilombos")
        cp["n_assentamentos"] = row.get("n_assentamentos")
        cp["n_barragens_dpa_alto"] = row.get("n_barragens_dpa_alto")
        cp["n_territorios_tradicionais"] = row.get("n_territorios_tradicionais")
        cp["cenario_dominante"] = row.get("cenario_dominante")
        cp["cuidados_territoriais"] = row.get("cuidados_territoriais")
        cp["rit_0_100"] = row.get("rit_0_100")
        cp["rit_faixa"] = row.get("rit_faixa")
        cp["rit_dominio_dominante"] = row.get("rit_dominio_dominante")
        cp["rit_completude_pct"] = row.get("rit_completude_pct")
        _attach_rit(cp, _rit_from_row(row))
        _geocalor_attach(cp, row)
        payloads.append(cp)

    return payloads


def payloads_to_dataframe(payloads: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for p in payloads:
        o = p.get("orientacoes") or {}
        pred = p.get("predicao") or {}
        rit = p.get("rit") or {}
        rows.append(
            {
                "escopo": p.get("escopo"),
                "alvo_id": p.get("alvo_id"),
                "alvo_nome": p.get("alvo_nome"),
                "nivel": p.get("nivel"),
                "icone": p.get("icone"),
                "titulo": p.get("titulo"),
                "n_municipios": p.get("n_municipios"),
                "motivo": p.get("motivo"),
                "nivel_predicao_7d": pred.get("nivel_predicao_7d"),
                "predicao_resumo": pred.get("resumo"),
                "rit_faixa": rit.get("rit_faixa") or rit.get("rit_faixa_pior"),
                "rit_0_100": rit.get("rit_0_100") or rit.get("rit_mediana"),
                "rit_dominio_dominante": rit.get("rit_dominio_dominante") or rit.get("dominio_moda"),
                "rit_resumo": rit.get("resumo"),
                "orientacao_gestor": o.get("gestor"),
                "orientacao_profissional": o.get("profissional"),
                "orientacao_populacao": o.get("populacao"),
                "n_indicadores": len(p.get("indicadores") or []),
                "n_prioritarios": len(p.get("municipios_prioritarios") or []),
                "gerado_em": p.get("gerado_em"),
            }
        )
    return pd.DataFrame(rows)


def render_payload_markdown(p: dict[str, Any]) -> str:
    lines = [
        f"# {p.get('titulo')}",
        "",
        f"**Escopo:** {p.get('escopo')} · **Alvo:** {p.get('alvo_nome')} · **Municípios:** {p.get('n_municipios')}",
        f"**Gerado em:** {p.get('gerado_em')}",
        "",
        "## Motivo",
        str(p.get("motivo") or "—"),
        "",
        "## Indicadores",
    ]
    for ind in p.get("indicadores") or []:
        lines.append(f"- **{ind.get('rotulo')}:** {ind.get('valor')}")
    pred = p.get("predicao") or {}
    rit = p.get("rit") or {}
    lines += [
        "",
        "## Predição (~7 dias)",
        f"{pred.get('icone_predicao', '')} {pred.get('resumo', '—')}",
        "",
        "## RIT multirisco (observado)",
        f"{rit.get('icone_rit', '🧭')} {rit.get('resumo', '—')}",
    ]
    if rit.get("explicacao_dominante"):
        lines.append(f"**Principal influenciador:** {rit.get('explicacao_dominante')}")
    if rit.get("dominios"):
        lines.append("")
        lines.append("### Classificação por domínio")
        for d in rit.get("dominios") or []:
            if d.get("status") == "valido":
                lines.append(
                    f"- **{d.get('rotulo')}:** {_fmt(d.get('score'), 0)}/100 · faixa {d.get('faixa')}"
                )
            elif d.get("status") == "omitido_defasagem":
                lines.append(f"- **{d.get('rotulo')}:** omitido por defasagem")
            else:
                lines.append(f"- **{d.get('rotulo')}:** indisponível")
    mun_rit = p.get("municipios_rit_prioritarios") or rit.get("municipios_rit_prioritarios") or []
    if mun_rit:
        lines.append("")
        lines.append("### Municípios com maior RIT (influenciadores)")
        for i, m in enumerate(mun_rit[:12], 1):
            lines.append(
                f"{i}. **{m.get('municipio')}** — RIT {_fmt(m.get('rit_0_100'), 0)} "
                f"({m.get('rit_faixa')}) · dominante: {m.get('rit_dominio_dominante_rotulo') or m.get('rit_dominio_dominante')} "
                f"· {m.get('radar_compacto') or '—'}"
            )
    if rit.get("dominantes_distribuicao_txt"):
        lines.append(f"**Distribuição de influenciadores:** {rit.get('dominantes_distribuicao_txt')}")
    lines += [
        "",
        "## Orientações",
        f"### Gestor\n{((p.get('orientacoes') or {}).get('gestor') or '—')}",
        "",
        f"### Profissionais de saúde\n{((p.get('orientacoes') or {}).get('profissional') or '—')}",
        "",
        f"### População\n{((p.get('orientacoes') or {}).get('populacao') or '—')}",
        "",
        "## Fontes",
        ", ".join(p.get("fontes") or []),
        "",
        "_ARARAS MT · CIEVS-MT / SES-MT._",
    ]
    return "\n".join(lines)


def persist_payloads(payloads: list[dict[str, Any]], table: str = "alertas_multinivel_v1") -> int:
    from sisclima.core.db import write_df

    df = payloads_to_dataframe(payloads)
    if df.empty:
        return 0
    write_df(df, table, if_exists="replace")
    return len(df)
