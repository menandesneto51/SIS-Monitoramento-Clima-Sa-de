# -*- coding: utf-8 -*-
"""Helpers da home operacional (hierarquia: situação → motivo → ação).

Não altera scores; só organiza o que o gestor vê primeiro.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from sisclima.core.db import read_table, table_exists
from sisclima.engines.recommendations import recommendations_for_stage
from sisclima.engines.rit_multirisco import DOMINIO_ROTULOS, scorecard_rit
from sisclima.engines.stages import STAGE_ORDER


AVISO_SINAL_VS_ATIVACAO = (
    "**Sinal do ARARAS MT ≠ ativação formal.** O nível e o boletim são critérios técnicos "
    "para avaliação do CIEVS/Sala de Situação. Não decretam COE, portaria nem emergência — "
    "isso depende de decisão documentada da autoridade competente."
)


def _max_data(df: pd.DataFrame | None, cols: list[str]) -> str | None:
    if df is None or df.empty:
        return None
    for c in cols:
        if c not in df.columns:
            continue
        s = pd.to_datetime(df[c], errors="coerce")
        if s.notna().any():
            return pd.Timestamp(s.max()).strftime("%Y-%m-%d %H:%M")
    return None


def build_fonte_frescor_home(resumo: pd.DataFrame | None = None) -> pd.DataFrame:
    """Tabela leve de frescor/cobertura para o topo do painel."""
    rows: list[dict[str, Any]] = []
    now = pd.Timestamp.now()

    def add(
        fonte: str,
        tabela: str,
        *,
        data_ref: str | None,
        munis: int | None,
        esperado_h: float,
        cobertura_nota: str,
    ) -> None:
        status = "indisponivel"
        if munis is not None and munis > 0 and not data_ref:
            status = "parcial"
        elif data_ref:
            try:
                age_h = (now - pd.to_datetime(data_ref)).total_seconds() / 3600.0
                if age_h <= esperado_h:
                    status = "atualizado"
                elif age_h <= esperado_h * 3:
                    status = "defasado"
                else:
                    status = "vencido"
            except Exception:
                status = "parcial"
        if munis is not None and munis > 0 and munis < 100 and status == "atualizado":
            status = "parcial"
        rows.append(
            {
                "fonte": fonte,
                "tabela": tabela,
                "data_referencia": data_ref or "—",
                "municipios": munis if munis is not None else "—",
                "status": status,
                "nota": cobertura_nota,
            }
        )

    resumo = resumo if resumo is not None else (read_table("resumo_municipal_atual") if table_exists("resumo_municipal_atual") else pd.DataFrame())
    n_resumo = int(len(resumo)) if resumo is not None and not resumo.empty else 0
    d_resumo = _max_data(resumo, ["data_processamento", "data_referencia", "atualizado_em"])
    add(
        "Resumo municipal",
        "resumo_municipal_atual",
        data_ref=d_resumo,
        munis=n_resumo,
        esperado_h=36,
        cobertura_nota="Núcleo operacional (142 esperado)",
    )

    for nome, tabela, cols, esperado, nota in [
        ("Open-Meteo / biometeo", "met_biometeo", ["data", "data_referencia", "time"], 36, "Clima horário/diário"),
        ("IndicaSUS / ocupação hospitalar", "hospital_ocupacao_municipio", ["data_processamento", "ultima_movimentacao"], 24, "Só mun. com hospital notificante"),
        ("SISREG / pressão hospitalar", "ops_sisreg_municipio", ["data_processamento", "atualizado_em"], 48, "Fila/regulação — demanda territorial"),
        ("Predição calor ~7d", "predicao_calor_7d_municipal_v6", ["data_processamento", "gerado_em", "data_referencia", "data"], 36, "Nowcast climático (não sazonal)"),
        ("SIVEP / SRAG", "epi_sivep_srag", ["data", "data_sintomas", "data_notificacao"], 72, "Respiratório"),
        ("Arboviroses", "epi_arboviroses_municipal", ["data", "data_referencia", "semana_epidemiologica"], 96, "Dengue/Zika/Chik"),
        ("INMET alertas", "inmet_alertas", ["inicio", "data_atualizacao", "gerado_em"], 24, "Alertas oficiais"),
        ("Cemaden", "cemaden_alertas", ["data_atualizacao", "data"], 24, "Desastres / hidrologia"),
        ("Qualidade do ar", "qualidade_ar_municipal", ["data", "data_referencia"], 48, "PM2,5 / IQA"),
        ("Skill clima 7d", "predicao_calor_7d_skill_resumo_v1", ["avaliado_em"], 72, "Acerto da regra 7d"),
        ("Nowcast epi", "epi_nowcast_municipal_v1", ["gerado_em"], 72, "Tendência SRAG/arbovírus auxiliar"),
    ]:
        df = read_table(tabela) if table_exists(tabela) else pd.DataFrame()
        mun = None
        if df is not None and not df.empty and "cod_ibge" in df.columns:
            mun = int(df["cod_ibge"].astype(str).str.extract(r"(\d+)")[0].nunique())
        add(
            nome,
            tabela,
            data_ref=_max_data(df, cols),
            munis=mun if mun is not None else (int(len(df)) if df is not None and not df.empty else 0),
            esperado_h=esperado,
            cobertura_nota=nota,
        )

    return pd.DataFrame(rows)


def frescor_resumo(frescor: pd.DataFrame) -> dict[str, Any]:
    if frescor is None or frescor.empty:
        return {"pct_ok": 0, "n_ok": 0, "n_total": 0, "n_problema": 0}
    st = frescor["status"].astype(str)
    n_total = len(frescor)
    n_ok = int(st.isin(["atualizado"]).sum())
    n_problema = int(st.isin(["vencido", "indisponivel", "parcial", "defasado"]).sum())
    return {
        "pct_ok": round(100.0 * n_ok / n_total, 0) if n_total else 0,
        "n_ok": n_ok,
        "n_total": n_total,
        "n_problema": n_problema,
    }


# Códigos internos → linguagem de gestor (alerta integrado / TITAN)
AMEACA_LABELS: dict[str, str] = {
    "sis_estagio": "Classificação ARARAS (calor)",
    "titan_calor": "Calor extremo (UTCI)",
    "titan_risco3d": "Risco cumulativo 3 dias",
    "titan_inmet": "Alerta INMET",
    "titan_cemaden": "Alerta Cemaden",
    "titan_solo": "Solo / estiagem ou saturação",
    "titan_hidro": "Nível de rio ANA",
    "estiagem_rio_baixo": "Estiagem / rio baixo (ANA)",
    "cheia_subida_rio": "Cheia / inundação (ANA)",
    "seca_baixa": "Seca — nível de rio baixo",
    "inundacao_alta": "Inundação — nível de rio alto",
    "calor": "Calor / onda de calor",
    "fumaça": "Fumaça / qualidade do ar",
    "ar": "Fumaça / qualidade do ar",
}


def rotulo_ameaca(codigo: str) -> str:
    raw = str(codigo or "").strip()
    if not raw:
        return "Sem dominante claro"
    key = raw.lower()
    if key in AMEACA_LABELS:
        return AMEACA_LABELS[key]
    # já veio legível (fallback por max de indicadores)
    if " " in raw or "/" in raw:
        return raw[:80]
    return AMEACA_LABELS.get(key, raw.replace("_", " ").strip()[:80])


def ameaca_dominante_estado(resumo: pd.DataFrame) -> str:
    """Rótulo curto e legível da principal ameaça estadual."""
    if resumo is None or resumo.empty:
        return "Dados insuficientes"
    if "componente_dominante" in resumo.columns:
        modo = (
            resumo["componente_dominante"]
            .dropna()
            .astype(str)
            .str.strip()
            .replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
            .dropna()
        )
        if not modo.empty:
            return rotulo_ameaca(str(modo.value_counts().index[0]))
    scores = {}
    for col, label in [
        ("risco_cumulativo_3d", "Calor / onda de calor"),
        ("pm25_ugm3", "Fumaça / qualidade do ar"),
        ("indice_saturacao_solo", "Solo / estiagem ou saturação"),
        ("incidencia_arbovirus_100k", "Arboviroses"),
        ("casos_srag", "SRAG / respiratório"),
        ("indice_pressao_saude", "Pressão assistencial"),
    ]:
        if col not in resumo.columns:
            continue
        s = pd.to_numeric(resumo[col], errors="coerce")
        if s.notna().any():
            scores[label] = float(s.max())
    if not scores:
        return "Síntese operacional (sem dominante claro)"
    return max(scores, key=scores.get)


# Escala de pressão assistencial (0–100); limiar "alta" = 70
PRESSAO_ESCALA_MAX = 100
PRESSAO_LIMIAR_ALTA = 70


def pressao_rotulo(media: float | None) -> str:
    if media is None or pd.isna(media):
        return "sem dado"
    if media < 30:
        return "baixa"
    if media < 50:
        return "moderada"
    if media < PRESSAO_LIMIAR_ALTA:
        return "alta"
    return "muito alta"


def pressao_card_value(media: float | None) -> str:
    """Ex.: '20/100' — valor na escala completa (perceptível no plantão)."""
    if media is None or pd.isna(media):
        return "—/100"
    return f"{float(media):.0f}/{PRESSAO_ESCALA_MAX}"


def pressao_card_caption(media: float | None) -> str:
    """Ex.: 'baixa · alta a partir de 70'."""
    rot = pressao_rotulo(media)
    if media is None or pd.isna(media):
        return rot
    return f"{rot} · alta ≥{PRESSAO_LIMIAR_ALTA}"


def tendencia_estado_rotulo(n_subindo: int, n_total: int) -> str:
    if n_total <= 0:
        return "sem dado"
    pct = 100.0 * n_subindo / n_total
    if pct >= 40:
        return "agravamento"
    if pct >= 15:
        return "agravamento parcial"
    if pct <= 5:
        return "estabilidade / redução"
    return "estabilidade"


def tendencia_card_value(n_subindo: int, n_total: int) -> str:
    """Ex.: '7/142' — municípios em piora sobre o total."""
    if n_total <= 0:
        return "—/—"
    return f"{int(n_subindo)}/{int(n_total)}"


def tendencia_card_caption(n_subindo: int, n_total: int) -> str:
    """Ex.: '5% em piora · estabilidade (agravamento ≥15%)'."""
    if n_total <= 0:
        return "sem dado"
    pct = 100.0 * n_subindo / n_total
    rot = tendencia_estado_rotulo(n_subindo, n_total)
    return f"{pct:.0f}% em piora · {rot} (agrava ≥15%)"


def _norm_nivel_series(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().str.strip()


def build_trajetoria_7d(
    resumo: pd.DataFrame | None,
    predicao: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Síntese atual × projeção ~7d (mesma lógica operacional do boletim El Niño)."""
    empty: dict[str, Any] = {
        "ok": False,
        "n_total": 0,
        "n_subindo": 0,
        "n_estavel": 0,
        "n_descendo": 0,
        "n_sobe_1": 0,
        "n_sobe_2mais": 0,
        "crit_atual": 0,
        "crit_proj": 0,
        "pct_subindo": 0.0,
        "pct_crit_atual": 0.0,
        "pct_crit_proj": 0.0,
        "rotulo": "sem dado",
        "callout_kind": "info",
        "proj_counts": {},
        "narrativa": "Trajetória ~7 dias indisponível nesta rodada (falta tendência ou predição).",
    }
    if resumo is None or resumo.empty:
        return empty

    df = resumo.copy()
    n = int(len(df))
    out = dict(empty)
    out["n_total"] = n

    # Tendência persistida no resumo (fonte do card da home).
    if "tendencia_7d" in df.columns:
        tend = _norm_nivel_series(df["tendencia_7d"])
        # Aceita variantes de acentuação.
        out["n_subindo"] = int(tend.isin(["subindo", "aumento", "↑", "subida"]).sum())
        out["n_estavel"] = int(tend.isin(["estável", "estavel", "manutenção", "manutencao", "→"]).sum())
        out["n_descendo"] = int(tend.isin(["descendo", "queda", "↓", "reducao", "redução"]).sum())

    # Nível projetado: tabela de predição (preferencial) ou coluna no resumo.
    proj = None
    if predicao is not None and not predicao.empty and "nivel_predicao_7d" in predicao.columns:
        pv = predicao.copy()
        if "cod_ibge" in df.columns and "cod_ibge" in pv.columns:
            df["_cod"] = df["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
            pv["_cod"] = pv["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
            m = df[["_cod", "nivel"]].merge(
                pv[["_cod", "nivel_predicao_7d"]].drop_duplicates("_cod"),
                on="_cod",
                how="left",
            )
            proj = _norm_nivel_series(m["nivel_predicao_7d"])
            atual = _norm_nivel_series(m["nivel"])
        else:
            proj = _norm_nivel_series(pv["nivel_predicao_7d"])
            atual = _norm_nivel_series(df["nivel"]) if "nivel" in df.columns else None
    elif "pred_nivel_clima_7d" in df.columns:
        proj = _norm_nivel_series(df["pred_nivel_clima_7d"])
        atual = _norm_nivel_series(df["nivel"]) if "nivel" in df.columns else None
    elif "nivel_predicao_7d" in df.columns:
        proj = _norm_nivel_series(df["nivel_predicao_7d"])
        atual = _norm_nivel_series(df["nivel"]) if "nivel" in df.columns else None
    else:
        atual = _norm_nivel_series(df["nivel"]) if "nivel" in df.columns else None

    if atual is not None:
        out["crit_atual"] = int(atual.isin(["vermelha", "roxa"]).sum())
        out["pct_crit_atual"] = 100.0 * out["crit_atual"] / max(n, 1)

    if proj is not None and proj.notna().any() and (proj != "nan").any():
        vc = proj.value_counts().to_dict()
        out["proj_counts"] = {str(k): int(v) for k, v in vc.items()}
        out["crit_proj"] = int(proj.isin(["vermelha", "roxa"]).sum())
        out["pct_crit_proj"] = 100.0 * out["crit_proj"] / max(n, 1)
        if atual is not None and len(atual) == len(proj):
            o_a = atual.map(STAGE_ORDER)
            o_p = proj.map(STAGE_ORDER)
            delta = o_p - o_a
            # Se tendencia_7d ausente, deriva do delta de classe.
            if out["n_subindo"] + out["n_estavel"] + out["n_descendo"] == 0:
                out["n_subindo"] = int((delta > 0).sum())
                out["n_estavel"] = int((delta == 0).sum())
                out["n_descendo"] = int((delta < 0).sum())
            out["n_sobe_1"] = int((delta == 1).sum())
            out["n_sobe_2mais"] = int((delta >= 2).sum())

    out["pct_subindo"] = 100.0 * out["n_subindo"] / max(n, 1)
    out["rotulo"] = tendencia_estado_rotulo(out["n_subindo"], n)
    if out["pct_subindo"] >= 40:
        out["callout_kind"] = "warn"
    elif out["pct_subindo"] >= 15:
        out["callout_kind"] = "tip"
    else:
        out["callout_kind"] = "info"

    out["ok"] = bool(out["n_subindo"] + out["n_estavel"] + out["n_descendo"] > 0 or out["crit_proj"] > 0)

    partes = [
        f"Trajetória ~7 dias ({out['rotulo']}): "
        f"{out['n_subindo']} de {n} ({out['pct_subindo']:.0f}%) municípios com elevação de classificação"
    ]
    if out["n_sobe_1"] or out["n_sobe_2mais"]:
        partes.append(
            f" ({out['n_sobe_1']} sobem 1 nível; {out['n_sobe_2mais']} sobem 2 ou mais)"
        )
    partes.append(
        f"; {out['n_estavel']} estáveis; {out['n_descendo']} com redução. "
        f"Vermelha+roxa: {out['crit_atual']}/{n} ({out['pct_crit_atual']:.0f}%) hoje → "
        f"{out['crit_proj']}/{n} ({out['pct_crit_proj']:.0f}%) na projeção."
    )
    pc = out["proj_counts"]
    if pc:
        partes.append(
            " Distribuição projetada: "
            f"verde {pc.get('verde', 0)}; amarela {pc.get('amarela', 0)}; "
            f"laranja {pc.get('laranja', 0)}; vermelha {pc.get('vermelha', 0)}; "
            f"roxa {pc.get('roxa', 0)}."
        )
    partes.append(
        " Leitura: cenário atual ≠ teto da semana — preparar assistência nos territórios "
        "já em vermelho/roxo e nos que sobem na projeção."
    )
    out["narrativa"] = "".join(partes)
    return out


def acao_recomendada_nivel(nivel: str, row: pd.Series | dict[str, Any] | None = None) -> str:
    """Ação operacional sugerida — contextual quando houver linha; sem ativação formal de COE."""
    if row is not None:
        try:
            from sisclima.engines.recommendations import acao_sugerida_contextual

            return acao_sugerida_contextual(row)
        except Exception:
            pass
    n = str(nivel or "cinza").lower()
    mapa = {
        "verde": "Manter monitoramento de rotina e revisar plano semanal.",
        "amarela": "Avaliar sala de situação municipal; checar insumos e grupos vulneráveis.",
        "laranja": "Acionar contato Regional/municipal; validar leitos e comunicação de risco (critérios técnicos).",
        "vermelha": "Priorizar regulação/leitos e reunião CIEVS — critérios para avaliação de resposta ampliada.",
        "roxa": "Elevar à Sala de Situação estadual: critérios técnicos persistentes para decisão documentada.",
        "cinza": "Completar dados antes de comunicar alerta definitivo.",
    }
    if n in mapa:
        return mapa[n]
    recs = recommendations_for_stage(n)
    if not recs:
        return "Manter monitoramento e validar no território."
    return f"{recs[0][0]}: {recs[0][1]}"


def cards_rit_estado(resumo: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Cards leigos do RIT para home / painel público (não altera nível operacional)."""
    if resumo is None or resumo.empty or "rit_0_100" not in resumo.columns:
        return [
            ("RIT multirisco", "—", "indisponível nesta rodada"),
            ("RIT vermelha+roxa", "—", "aguarde enrich"),
            ("Domínio dominante", "—", "máximo entre fatores válidos"),
        ]
    df = resumo.copy()
    n = max(len(df), 1)
    crit = 0
    if "rit_faixa" in df.columns:
        crit = int(df["rit_faixa"].astype(str).str.lower().isin(["vermelha", "roxa"]).sum())
    med = pd.to_numeric(df["rit_0_100"], errors="coerce").median()
    med_txt = "—" if pd.isna(med) else f"{float(med):.0f}"
    dom = "—"
    if "rit_dominio_dominante" in df.columns:
        vc = (
            df["rit_dominio_dominante"]
            .astype(str)
            .str.lower()
            .replace({"nan": None, "none": None, "—": None, "-": None})
            .dropna()
        )
        if not vc.empty:
            top_id = vc.value_counts().index[0]
            dom = DOMINIO_ROTULOS.get(str(top_id), str(top_id))
    comp = None
    if "rit_completude_pct" in df.columns:
        comp = pd.to_numeric(df["rit_completude_pct"], errors="coerce").median()
    comp_txt = f"completude med. {float(comp):.0f}%" if comp is not None and not pd.isna(comp) else "observado multirisco"
    return [
        ("RIT mediano (0–100)", med_txt, comp_txt),
        ("RIT vermelha+roxa", f"{crit}/{n}", f"{100.0 * crit / n:.0f}% do recorte"),
        ("Domínio mais frequente", str(dom), "fator que mais puxa o RIT no recorte"),
    ]


def cards_ehf_geocalor(resumo: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Cards leigos do EHF GeoCalor (Fiocruz) para a Visão."""
    if resumo is None or resumo.empty:
        return [
            ("EHF GeoCalor", "—", "indisponível"),
            ("Onda ativa", "—", "sem join STAR"),
            ("Referência", "—", "rode ETL STAR/GeoCalor"),
        ]
    df = resumo.copy()
    n = max(len(df), 1)
    ehf = pd.to_numeric(df.get("ehf_geocalor", df.get("ehf")), errors="coerce")
    n_pos = int((ehf.fillna(0) > 0).sum()) if ehf is not None else 0
    n_onda = (
        int(pd.to_numeric(df["onda_geocalor_ativa"], errors="coerce").fillna(0).gt(0).sum())
        if "onda_geocalor_ativa" in df.columns
        else int(pd.to_numeric(df.get("is_hw_day"), errors="coerce").fillna(0).gt(0).sum())
        if "is_hw_day" in df.columns
        else 0
    )
    mx = float(ehf.max()) if ehf is not None and ehf.notna().any() else None
    data_ref = "—"
    if "data_ehf_geocalor" in df.columns and df["data_ehf_geocalor"].notna().any():
        data_ref = str(df["data_ehf_geocalor"].dropna().astype(str).mode().iloc[0])
    idade = None
    if "ehf_geocalor_idade_dias" in df.columns and df["ehf_geocalor_idade_dias"].notna().any():
        idade = int(pd.to_numeric(df["ehf_geocalor_idade_dias"], errors="coerce").dropna().mode().iloc[0])
    idade_txt = f"defasagem {idade}d" if idade is not None else "Nairn & Fawcett / Fiocruz"
    return [
        ("EHF máximo", "—" if mx is None else f"{mx:.2f}", idade_txt),
        ("Onda GeoCalor ativa", f"{n_onda}/{n}", f"EHF > 0 no recorte: {n_pos}"),
        ("Data GeoCalor", data_ref, "STAR → resumo → RIT/alertas"),
    ]


def cards_rit_dominios(resumo: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Mediana dos scores RIT por domínio + alerta de completude."""
    if resumo is None or resumo.empty:
        return [
            ("RIT térmico", "—", "indisponível"),
            ("RIT ar / EHF", "—", "indisponível"),
            ("Completude RIT", "—", "rode enrich"),
        ]
    df = resumo.copy()
    cols = [
        ("rit_score_termico", "RIT térmico"),
        ("rit_score_ar", "RIT ar/PM2,5"),
        ("rit_score_ehf", "RIT EHF"),
        ("rit_score_hidro", "RIT hidro"),
        ("rit_score_pressao", "RIT pressão"),
        ("rit_score_rede", "RIT fragilidade rede"),
    ]
    cards: list[tuple[str, str, str]] = []
    for col, rot in cols:
        if col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        if not s.notna().any():
            cards.append((rot, "—", "domínio omitido/indisponível"))
            continue
        med = float(s.median())
        n_ok = int(s.notna().sum())
        cards.append((rot, f"{med:.0f}", f"mediana · n={n_ok}"))
    comp = None
    if "rit_completude_pct" in df.columns:
        comp = pd.to_numeric(df["rit_completude_pct"], errors="coerce").median()
    if comp is not None and not pd.isna(comp):
        nota = "OK" if float(comp) >= 60 else "abaixo de 60% — revisar fontes"
        cards.append(("Completude RIT", f"{float(comp):.0f}%", nota))
    return cards[:7] if cards else [("RIT por domínio", "—", "sem colunas rit_score_*")]


def tabela_divergencia_pred_rit(
    resumo: pd.DataFrame,
    predicao: pd.DataFrame | None = None,
    n: int = 10,
) -> pd.DataFrame:
    """Top N municípios com divergência nivel × pred 7d × RIT (só leitura)."""
    if resumo is None or resumo.empty:
        return pd.DataFrame()
    df = resumo.copy()
    if predicao is not None and not predicao.empty and "nivel_predicao_7d" in predicao.columns:
        pv = predicao.copy()
        if "cod_ibge" in df.columns and "cod_ibge" in pv.columns:
            df["_cod"] = df["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
            pv["_cod"] = pv["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
            keep = ["_cod", "nivel_predicao_7d"]
            if "risco_preditivo_score" in pv.columns:
                keep.append("risco_preditivo_score")
            df = df.merge(pv[keep].drop_duplicates("_cod"), on="_cod", how="left", suffixes=("", "_pred"))
    if "nivel_predicao_7d" not in df.columns and "pred_nivel_clima_7d" in df.columns:
        df["nivel_predicao_7d"] = df["pred_nivel_clima_7d"]
    if "rit_0_100" not in df.columns or "nivel" not in df.columns:
        return pd.DataFrame()

    def _ord(s: pd.Series) -> pd.Series:
        return s.astype(str).str.lower().map(STAGE_ORDER).fillna(-1)

    niv = _ord(df["nivel"])
    pred = _ord(df["nivel_predicao_7d"]) if "nivel_predicao_7d" in df.columns else pd.Series([-1] * len(df))
    rit = pd.to_numeric(df["rit_0_100"], errors="coerce")
    # Faixa RIT em ordem de estágio aproximada
    rit_ord = (
        df.get("rit_faixa", pd.Series(["cinza"] * len(df)))
        .astype(str)
        .str.lower()
        .map(STAGE_ORDER)
        .fillna(-1)
    )
    # Divergência: |nivel - pred| + |rit_faixa - nivel| + boost se RIT alto e pred baixa
    gap = (niv - pred).abs().fillna(0) + (rit_ord - niv).abs().fillna(0)
    rit_alto_pred_baixa = (rit.fillna(0) >= 70) & (pred <= 1)
    niv_baixo_rit_alto = (niv <= 1) & (rit.fillna(0) >= 70)
    gap = gap + rit_alto_pred_baixa.astype(int) * 2 + niv_baixo_rit_alto.astype(int) * 2
    df = df.assign(_gap=gap, _rit=rit)
    top = df[df["_gap"] > 0].sort_values(["_gap", "_rit"], ascending=False).head(int(n))
    if top.empty:
        return pd.DataFrame()

    def _mun(r: pd.Series) -> str:
        m = r.get("municipio")
        if pd.notna(m) and str(m).strip() and str(m).lower() not in {"nan", "none"}:
            return str(m)
        return str(r.get("cod_ibge") or "—")

    return pd.DataFrame(
        {
            "Município": [_mun(r) for _, r in top.iterrows()],
            "Nível": top["nivel"].astype(str).str.lower().values,
            "Pred ~7d": top.get("nivel_predicao_7d", pd.Series(["—"] * len(top))).astype(str).str.lower().values,
            "RIT": [f"{float(v):.0f}" if pd.notna(v) else "—" for v in top["_rit"]],
            "Faixa RIT": top.get("rit_faixa", pd.Series(["—"] * len(top))).astype(str).str.lower().values,
            "Dominante": [
                DOMINIO_ROTULOS.get(str(r.get("rit_dominio_dominante") or "").lower(), str(r.get("rit_dominio_dominante") or "—"))
                for _, r in top.iterrows()
            ],
            "Gap": top["_gap"].astype(int).values,
            "Ação sugerida": [acao_recomendada_nivel(str(r.get("nivel") or "cinza"), r) for _, r in top.iterrows()],
        }
    )


def cards_compostos_sala(resumo: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Cards leigos dos indicadores compostos (fumaça, pressão×RIT/IRM, gap nebulização)."""
    if resumo is None or resumo.empty:
        return [
            ("Fumaça sem PM", "—", "aguardando enrich"),
            ("Pressão × RIT", "—", "divergentes"),
            ("Gap fumaça×nebul", "—", "CNES nebulização"),
            ("Completude Sala", "—", "fontes críticas"),
        ]
    n = max(len(resumo), 1)
    n_fum = (
        int(pd.to_numeric(resumo["sinal_fumaca_sem_pm"], errors="coerce").fillna(0).sum())
        if "sinal_fumaca_sem_pm" in resumo.columns
        else 0
    )
    n_intox = (
        int(pd.to_numeric(resumo["n_intox_fumaca_7d"], errors="coerce").fillna(0).gt(0).sum())
        if "n_intox_fumaca_7d" in resumo.columns
        else 0
    )
    n_px = int(resumo["pressao_x_rit"].notna().sum()) if "pressao_x_rit" in resumo.columns else 0
    n_gap = (
        int(pd.to_numeric(resumo["gap_fumaca_nebulizacao"], errors="coerce").fillna(0).sum())
        if "gap_fumaca_nebulizacao" in resumo.columns
        else 0
    )
    n_pr = (
        int(resumo["pressao_x_resiliencia"].notna().sum())
        if "pressao_x_resiliencia" in resumo.columns
        else 0
    )
    comp = (
        pd.to_numeric(resumo["completude_sala_pct"], errors="coerce").median()
        if "completude_sala_pct" in resumo.columns
        else None
    )
    comp_txt = f"{float(comp):.0f}%" if comp is not None and not pd.isna(comp) else "—"
    nota = "OK" if comp is not None and not pd.isna(comp) and float(comp) >= 60 else "revisar fontes"
    fum_nota = "focos/PM ou SINAN intox 7d" if n_intox else "focos>0 e PM nulo"
    return [
        ("Fumaça / intox", f"{n_fum}/{n}", fum_nota),
        ("Pressão × RIT divergente", f"{n_px}/{n}", "faixas discordantes"),
        ("Gap fumaça × nebulização", f"{n_gap}/{n}", "sinal sem nebulizador"),
        ("Pressão × resiliência", f"{n_pr}/{n}", "pressão vs faixa IRM"),
        ("Completude Sala", comp_txt, nota),
    ]


def cards_irm_resiliencia(resumo: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Cards do Índice de Resiliência Municipal (capacidade CNES; inverso no RIT rede)."""
    if resumo is None or resumo.empty:
        return [
            ("IRM mediano", "—", "capacidade CNES 0–100"),
            ("IRM baixa", "—", "municípios frágeis"),
            ("Completude IRM", "—", "componentes com dado"),
        ]
    n = max(len(resumo), 1)
    irm = (
        pd.to_numeric(resumo["indice_resiliencia_municipal_0_100"], errors="coerce")
        if "indice_resiliencia_municipal_0_100" in resumo.columns
        else None
    )
    if irm is None or not irm.notna().any():
        return [
            ("IRM mediano", "—", "CNES/IRM indisponível"),
            ("IRM baixa", "—", "rode enrich com USE_DW_CNES"),
            ("Completude IRM", "—", "mín. 40% componentes"),
        ]
    med = float(irm.median())
    n_baixa = int((resumo.get("irm_faixa", pd.Series(dtype=object)).astype(str).str.lower() == "baixa").sum()) if "irm_faixa" in resumo.columns else int((irm < 25).sum())
    comp = (
        pd.to_numeric(resumo["irm_completude_pct"], errors="coerce").median()
        if "irm_completude_pct" in resumo.columns
        else None
    )
    rede = (
        pd.to_numeric(resumo["rit_score_rede"], errors="coerce").median()
        if "rit_score_rede" in resumo.columns
        else None
    )
    rede_txt = f"fragilidade RIT med. {float(rede):.0f}" if rede is not None and not pd.isna(rede) else "fragilidade = 100−IRM"
    comp_txt = f"{float(comp):.0f}%" if comp is not None and not pd.isna(comp) else "—"
    return [
        ("IRM mediano (0–100)", f"{med:.0f}", rede_txt),
        ("IRM baixa", f"{n_baixa}/{n}", "capacidade frágil no recorte"),
        ("Completude IRM", comp_txt, "alto = melhor capacidade"),
    ]


def cards_agravos_extras_clima(resumo: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Cards SINAN extras clima (DW) + fonte SRAG + internações CID."""
    if resumo is None or resumo.empty:
        return [
            ("Extras clima DW", "—", "aguardando enrich"),
            ("Fonte SRAG", "—", "local preferencial"),
            ("Internações CID clima", "—", "IndicaSUS/DW"),
        ]
    n = max(len(resumo), 1)
    extras = (
        int(pd.to_numeric(resumo["casos_extras_clima_7d"], errors="coerce").fillna(0).gt(0).sum())
        if "casos_extras_clima_7d" in resumo.columns
        else 0
    )
    total_extras = (
        int(pd.to_numeric(resumo["casos_extras_clima_7d"], errors="coerce").fillna(0).sum())
        if "casos_extras_clima_7d" in resumo.columns
        else 0
    )
    fonte = "indisponivel"
    if "fonte_srag" in resumo.columns:
        vals = resumo["fonte_srag"].dropna().astype(str)
        if not vals.empty:
            fonte = str(vals.mode().iloc[0]) if len(vals.mode()) else str(vals.iloc[0])
    rotulo_fonte = {
        "sivep_local": "SIVEP local",
        "sinan_dw_srag": "SINAN DW (fallback)",
        "indisponivel": "indisponível",
    }.get(fonte, fonte)
    intern = (
        int(pd.to_numeric(resumo["internacoes_cid_clima_7d"], errors="coerce").fillna(0).sum())
        if "internacoes_cid_clima_7d" in resumo.columns
        else 0
    )
    n_intern_mun = (
        int(pd.to_numeric(resumo["internacoes_cid_clima_7d"], errors="coerce").fillna(0).gt(0).sum())
        if "internacoes_cid_clima_7d" in resumo.columns
        else 0
    )
    return [
        ("Extras clima (mun.)", f"{extras}/{n}", f"{total_extras} casos 7d DW"),
        ("Fonte SRAG", rotulo_fonte, "local preferencial; DW se vazio"),
        ("Internações CID 7d", f"{intern}", f"{n_intern_mun} mun. com registro"),
    ]


def cards_onda2_rede_malaria(resumo: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Cards Onda 2: malária DW + nebulização CNES (resiliência)."""
    if resumo is None or resumo.empty:
        return [
            ("Malária 7d", "—", "USE_DW_SIVEP"),
            ("Nebulizadores CNES", "—", "USE_DW_CNES"),
            ("Equipamentos CNES", "—", "competência atual"),
        ]
    n = max(len(resumo), 1)
    mal_mun = (
        int(pd.to_numeric(resumo["casos_malaria_7d"], errors="coerce").fillna(0).gt(0).sum())
        if "casos_malaria_7d" in resumo.columns
        else 0
    )
    mal_tot = (
        int(pd.to_numeric(resumo["casos_malaria_7d"], errors="coerce").fillna(0).sum())
        if "casos_malaria_7d" in resumo.columns
        else 0
    )
    mal_nota = "DW"
    if "malaria_janela" in resumo.columns and resumo["malaria_janela"].notna().any():
        mal_nota = str(resumo["malaria_janela"].dropna().iloc[0])
    neb = (
        int(pd.to_numeric(resumo["equipamentos_nebulizacao"], errors="coerce").fillna(0).sum())
        if "equipamentos_nebulizacao" in resumo.columns
        else 0
    )
    eq = (
        int(pd.to_numeric(resumo["equipamentos_total"], errors="coerce").fillna(0).sum())
        if "equipamentos_total" in resumo.columns
        else 0
    )
    return [
        ("Malária (mun.)", f"{mal_mun}/{n}", f"{mal_tot} · {mal_nota}"),
        ("Nebulizadores CNES", f"{neb}", "tipo/grupo NEBUL"),
        ("Equipamentos CNES", f"{eq}", "soma municipal"),
    ]


def cards_onda3_cnes_rede(resumo: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Cards Onda 3: profissionais, eAB e serviços CNES (só contagens)."""
    if resumo is None or resumo.empty:
        return [
            ("Profissionais CNES", "—", "contagens municipais"),
            ("Equipes eAB", "—", "atenção básica"),
            ("Serviços CNES", "—", "classificação"),
        ]
    n = max(len(resumo), 1)
    prof = (
        int(pd.to_numeric(resumo["cnes_profissionais_qtd"], errors="coerce").fillna(0).sum())
        if "cnes_profissionais_qtd" in resumo.columns
        else 0
    )
    prof_mun = (
        int(pd.to_numeric(resumo["cnes_profissionais_qtd"], errors="coerce").fillna(0).gt(0).sum())
        if "cnes_profissionais_qtd" in resumo.columns
        else 0
    )
    eab = (
        int(pd.to_numeric(resumo["cnes_equipes_ab_qtd"], errors="coerce").fillna(0).sum())
        if "cnes_equipes_ab_qtd" in resumo.columns
        else 0
    )
    povos = (
        int(pd.to_numeric(resumo["cnes_equipes_ab_povos_tradicionais"], errors="coerce").fillna(0).sum())
        if "cnes_equipes_ab_povos_tradicionais" in resumo.columns
        else 0
    )
    svc = (
        int(pd.to_numeric(resumo["cnes_servicos_classificacao_qtd"], errors="coerce").fillna(0).sum())
        if "cnes_servicos_classificacao_qtd" in resumo.columns
        else 0
    )
    return [
        ("Profissionais CNES", f"{prof}", f"{prof_mun}/{n} mun."),
        ("Equipes eAB", f"{eab}", f"povos trad. {povos}"),
        ("Serviços CNES", f"{svc}", "classificação municipal"),
    ]


def cards_vigilancia_ops(resumo: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Cards SISAGUA / entomologia / denúncias (lacuna explícita se sem carga)."""
    if resumo is None or resumo.empty:
        return [
            ("SISAGUA", "—", "aguardando carga"),
            ("Entomologia", "—", "aguardando carga"),
            ("Denúncias", "—", "aguardando carga"),
        ]
    n = max(len(resumo), 1)
    cards: list[tuple[str, str, str]] = []
    if "sisagua_monitoramento_valido" in resumo.columns:
        ok = int(pd.to_numeric(resumo["sisagua_monitoramento_valido"], errors="coerce").fillna(0).gt(0).sum())
        cards.append(("SISAGUA válido", f"{ok}/{n}", "monitoramento municipal"))
    else:
        cards.append(("SISAGUA", "sem carga", "CSV ops_sisagua ausente"))
    if "entomologia_iip" in resumo.columns:
        alto = int(pd.to_numeric(resumo["entomologia_iip"], errors="coerce").fillna(0).gt(3.9).sum())
        cards.append(("Entomologia IIP>3,9", f"{alto}/{n}", "LIRAa / ovitrampa"))
    else:
        cards.append(("Entomologia", "sem carga", "CSV ops_entomologia ausente"))
    if "denuncias_sla_ok" in resumo.columns or "denuncias_sla_pct" in resumo.columns:
        if "denuncias_sla_ok" in resumo.columns:
            ok = int(pd.to_numeric(resumo["denuncias_sla_ok"], errors="coerce").fillna(0).eq(1).sum())
            cards.append(("Denúncias SLA OK", f"{ok}/{n}", "Visa / COVSAN"))
        else:
            med = pd.to_numeric(resumo["denuncias_sla_pct"], errors="coerce").median()
            cards.append(("Denúncias SLA %", f"{float(med):.0f}%" if pd.notna(med) else "—", "Visa / COVSAN"))
    else:
        cards.append(("Denúncias", "sem carga", "CSV ops_denuncias ausente"))
    return cards


def tabela_prioridades_hoje(resumo: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Top N municípios para contato do plantão (1 linha = 1 decisão)."""
    if resumo is None or resumo.empty:
        return pd.DataFrame()
    df = resumo.copy()
    # Nome municipal: evita NaN quando a coluna veio como float/código
    if "municipio" in df.columns:
        mun = df["municipio"]
        bad = mun.isna() | mun.astype(str).str.strip().str.lower().isin(["", "nan", "none", "nat"])
        if bad.mean() > 0.3 and "cod_ibge" in df.columns:
            try:
                from sisclima.ingestion.ibge_municipios import load_or_refresh_municipios

                cat = load_or_refresh_municipios()
                if cat is not None and not cat.empty and "municipio" in cat.columns:
                    cat = cat.copy()
                    cat["cod_ibge"] = cat["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
                    df["cod_ibge"] = df["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
                    m = cat[["cod_ibge", "municipio"]].drop_duplicates("cod_ibge")
                    if "regional_saude" in cat.columns and (
                        "regional_saude" not in df.columns
                        or df["regional_saude"].isna().mean() > 0.3
                    ):
                        m = cat[["cod_ibge", "municipio", "regional_saude"]].drop_duplicates("cod_ibge")
                    df = df.drop(columns=[c for c in m.columns if c != "cod_ibge" and c in df.columns], errors="ignore")
                    df = df.merge(m, on="cod_ibge", how="left")
            except Exception:
                pass
        bad = df["municipio"].isna() | df["municipio"].astype(str).str.strip().str.lower().isin(
            ["", "nan", "none", "nat"]
        )
        if bad.any() and "cod_ibge" in df.columns:
            df.loc[bad, "municipio"] = df.loc[bad, "cod_ibge"].astype(str)
        df["municipio"] = df["municipio"].astype(str)
    elif "cod_ibge" in df.columns:
        df["municipio"] = df["cod_ibge"].astype(str)
    else:
        df["municipio"] = "—"

    if "regional_saude" in df.columns:
        df["regional_saude"] = df["regional_saude"].fillna("—").astype(str)
    else:
        df["regional_saude"] = "—"

    if "nivel" in df.columns:
        df["_rank"] = df["nivel"].astype(str).str.lower().map(STAGE_ORDER).fillna(-1)
    else:
        df["_rank"] = 0
    sort_cols = [c for c in ["_rank", "indice_prioridade_global", "score", "risco_cumulativo_3d"] if c in df.columns]
    top = df.sort_values(sort_cols, ascending=False).head(int(n)).copy()

    def _motivo(row: pd.Series) -> str:
        for c in ("motivo", "motivo_integrado", "componente_dominante", "orientacao_leiga"):
            v = row.get(c)
            if pd.notna(v) and str(v).strip() and str(v).lower() not in {"nan", "none", "—"}:
                return str(v)[:120]
        return "—"

    def _fmt_num(v: Any, suffix: str = "") -> str:
        try:
            if v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v):
                return "—"
            return f"{float(v):.0f}{suffix}"
        except Exception:
            return "—"

    def _radar_cell(row: pd.Series) -> str:
        raw = row.get("radar_compacto")
        if pd.notna(raw) and str(raw).strip() and str(raw).lower() not in {"nan", "none", "—"}:
            return str(raw)
        if "rit_0_100" not in top.columns and "rit_score_termico" not in top.columns:
            return "—"
        try:
            return str(scorecard_rit(row.to_dict()).get("radar_compacto") or "—")
        except Exception:
            return "—"

    def _lacunas(row: pd.Series) -> str:
        flags: list[str] = []
        occ = row.get("ocupacao_leitos_pct")
        fonte = str(row.get("fonte_ocupacao") or "").strip().lower()
        if occ is None or (isinstance(occ, float) and pd.isna(occ)) or pd.isna(occ):
            if "sem_leitos" in fonte:
                flags.append("sem hospital IndicaSUS")
            else:
                flags.append("sem ocupação IndicaSUS")
        elif any(x in fonte for x in ("proxy", "estim", "fallback", "estado")):
            flags.append("ocupação estimada (legado)")
        sis = row.get("kpi_sisreg_solicitacoes")
        sis_ok = row.get("kpi_sisreg_disponivel")
        if sis_ok is False or (
            (sis is None or (isinstance(sis, float) and pd.isna(sis)) or pd.isna(sis))
            and not bool(sis_ok)
        ):
            flags.append("sem pressão SISREG")
        cap = row.get("indice_capacidade_cnes")
        leitos = row.get("cnes_leitos_total")
        if (cap is None or pd.isna(cap)) and (leitos is None or pd.isna(leitos)):
            flags.append("CNES vazio")
        res = row.get("indice_resiliencia")
        if res is None or pd.isna(res):
            res = row.get("indice_resiliencia_proxy")
        try:
            if res is not None and not pd.isna(res) and float(res) < 40:
                flags.append("baixa resiliência")
        except Exception:
            pass
        if int(row.get("flag_persistencia_roxa") or 0) == 1:
            flags.append("persistência roxa")
        return "; ".join(flags) if flags else "—"

    resil_col = (
        top["indice_resiliencia"]
        if "indice_resiliencia" in top.columns
        else top.get("indice_resiliencia_proxy", pd.Series([None] * len(top)))
    )
    cap_col = top.get("indice_capacidade_cnes", pd.Series([None] * len(top)))
    occ_col = top.get("ocupacao_leitos_pct", pd.Series([None] * len(top)))
    sis_col = top.get("kpi_sisreg_solicitacoes", pd.Series([None] * len(top)))

    def _fmt_ocup(row_i: int, v: Any) -> str:
        txt = _fmt_num(v, "%")
        if txt == "—":
            return "—"
        try:
            fonte = str(top.iloc[row_i].get("fonte_ocupacao") or "")
            if "TEMPO_REAL" in fonte.upper():
                return txt
        except Exception:
            pass
        return txt

    out = pd.DataFrame(
        {
            "Município": top["municipio"].values,
            "Regional": top["regional_saude"].values,
            "Nível": top.get("nivel", pd.Series(["cinza"] * len(top))).astype(str).str.lower().values,
            "RIT": [
                _fmt_num(r.get("rit_0_100")) if "rit_0_100" in top.columns else "—"
                for _, r in top.iterrows()
            ],
            "Faixa RIT": (
                top.get("rit_faixa", pd.Series(["—"] * len(top))).astype(str).str.lower().values
                if "rit_faixa" in top.columns
                else ["—"] * len(top)
            ),
            "Dominante RIT": [
                DOMINIO_ROTULOS.get(
                    str(r.get("rit_dominio_dominante") or "").lower(),
                    str(r.get("rit_dominio_dominante") or "—"),
                )
                if "rit_dominio_dominante" in top.columns
                else "—"
                for _, r in top.iterrows()
            ],
            "Radar RIT": [
                _radar_cell(r) for _, r in top.iterrows()
            ],
            "Principal motivo": [_motivo(r) for _, r in top.iterrows()],
            "Tendência": top.get("tendencia_7d", top.get("tendencia_prioridade_7d", pd.Series(["—"] * len(top))))
            .astype(str)
            .values,
            "Ocupação IndicaSUS": [_fmt_ocup(i, v) for i, v in enumerate(occ_col)],
            "Pressão SISREG": [_fmt_num(v) for v in sis_col],
            "Capacidade CNES": [_fmt_num(v) for v in cap_col],
            "Resiliência": [_fmt_num(v) for v in resil_col],
            "Lacunas": [_lacunas(r) for _, r in top.iterrows()],
            "Ação recomendada": [
                acao_recomendada_nivel(str(r.get("nivel") or "cinza"), r) for _, r in top.iterrows()
            ],
        }
    )
    return out.reset_index(drop=True)


def explicar_nivel_municipio(row: pd.Series | dict[str, Any]) -> str:
    """Texto curto 'por que este nível' a partir das colunas já existentes."""
    r = row if isinstance(row, dict) else row.to_dict()
    nivel = str(r.get("nivel") or "—")
    score = r.get("score")
    motivo = str(r.get("motivo") or r.get("motivo_integrado") or "—")
    lines = [
        f"**Nível:** {nivel} · **Pontuação:** {score if score is not None else '—'}/4",
        f"**Motivo (pipeline):** {motivo}",
    ]
    for label, key, fmt in [
        ("Tmáx", "tmax", "{:.1f} °C"),
        ("Sensação (UTCI proxy)", "utci_proxy", "{:.1f}"),
        ("Risco calor 3d", "risco_cumulativo_3d", "{:.1f}"),
        ("PM2,5", "pm25_ugm3", "{:.1f} µg/m³"),
        ("Casos SRAG (janela)", "casos_srag", "{:.0f}"),
        ("Z-score SRAG", "zscore_srag", "{:.2f}"),
        ("P(aumento) SRAG aux.", "srag_p_aumento", "{:.0%}"),
        ("Arbovírus 7d", "casos_arbovirus_7d", "{:.0f}"),
        ("P(aumento) arbovírus aux.", "arbo_p_aumento", "{:.0%}"),
        ("Nowcast epi", "nowcast_alerta", "{}"),
        ("Ocupação hospitalar (IndicaSUS)", "ocupacao_leitos_pct", "{:.1f}%"),
        ("Fonte ocupação", "fonte_ocupacao", "{}"),
        ("Pressão hospitalar SISREG (solicitações)", "kpi_sisreg_solicitacoes", "{:.0f}"),
        ("Semáforo SISREG", "kpi_sisreg_semaforo", "{}"),
        ("Índice pressão 0–100", "indice_pressao_saude", "{:.1f}"),
        ("Capacidade CNES", "indice_capacidade_cnes", "{:.0f}"),
        ("Resiliência", "indice_resiliencia", "{:.0f}"),
        ("Persistência roxa", "flag_persistencia_roxa", "{}"),
        ("Pressão calor (proxy)", "pressao_calor_pct", "{:.1f}"),
        ("Completude dados", "completude_dados_pct", "{:.0f}%"),
    ]:
        v = r.get(key)
        if key == "indice_resiliencia" and (v is None or (isinstance(v, float) and pd.isna(v))):
            v = r.get("indice_resiliencia_proxy")
        if v is None or (isinstance(v, float) and pd.isna(v)):
            if key == "ocupacao_leitos_pct":
                fonte = str(r.get("fonte_ocupacao") or "")
                if "SEM_LEITOS" in fonte.upper():
                    lines.append("- Ocupação hospitalar (IndicaSUS): sem hospital notificante (esperado)")
            continue
        try:
            if key == "flag_persistencia_roxa":
                if int(v or 0) == 1:
                    lines.append("- Persistência roxa: sim (EHF/onda ≥ limiar de dias)")
                continue
            if key == "fonte_ocupacao":
                lines.append(f"- Fonte ocupação: {v}")
                continue
            if "{:" in fmt:
                lines.append(f"- {label}: {fmt.format(float(v))}")
            else:
                lines.append(f"- {label}: {v}")
        except Exception:
            lines.append(f"- {label}: {v}")
    lines.append(f"**Ação sugerida:** {acao_recomendada_nivel(nivel, r)}")
    lines.append(
        "_Ocupação IndicaSUS ≠ pressão SISREG. Ausência de leitos notificados ≠ risco zero — use a fila/regulação._"
    )
    try:
        sc = scorecard_rit(r)
        if sc.get("disponivel"):
            lines.append("")
            lines.append(
                f"**RIT (multirisco observado):** {sc.get('rit_0_100'):.0f}/100 · faixa {sc.get('rit_faixa')}"
            )
            lines.append(f"- {sc.get('explicacao_dominante')}")
            if sc.get("radar_compacto"):
                lines.append(f"- Radar: {sc.get('radar_compacto')}")
            if sc.get("rit_pressao_omitida_defasagem"):
                lines.append("- Pressão assistencial omitida (fonte defasada >14 dias).")
            lines.append(
                "_RIT ≠ nível operacional e ≠ predição térmica ~7 dias — produto paralelo para leitura multirisco._"
            )
        elif sc.get("dominios"):
            lines.append("")
            lines.append(f"**RIT:** indisponível — {sc.get('explicacao_dominante')}")
    except Exception:
        pass
    return "\n".join(lines)
