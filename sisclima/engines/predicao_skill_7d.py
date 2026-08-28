# -*- coding: utf-8 -*-
"""Skill da predição operacional 7d + ML auxiliar (não altera o nível SES).

Fase 1 — avalia a regra (persistência histórica + arquivo de emissões).
Fase 2 — probabilidade auxiliar por município; `nivel_predicao_7d` continua da regra.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from sisclima.core.db import read_table, write_df
from sisclima.core.logging_utils import get_logger
from sisclima.engines.stages import STAGE_ORDER

log = get_logger(__name__)

LEVEL_ORDER = ["cinza", "verde", "amarela", "laranja", "vermelha", "roxa"]
LEVELS_PRED = ["verde", "amarela", "laranja", "vermelha", "roxa"]
FEAT_COLS = [
    "tmax_max_7d",
    "utci_proxy_max_7d",
    "risco_cumulativo_3d_max_7d",
    "dias_onda_calor_prevista_7d",
]

# Componentes do RISCO_TÉRMICO_PROJETADO (0–100). Combinação = máximo (sem soma).
# Documentação operacional no boletim: quadro “Como a classe projetada é calculada”.
_LIMIARES_INTENSIDADE_TMAX = ((34.0, 25), (37.0, 50), (40.0, 75), (42.0, 100))
_LIMIARES_ESTRESSE_UTCI = ((32.0, 25), (36.0, 50), (40.0, 75), (44.0, 100))
_LIMIARES_PERSISTENCIA = ((3.0, 25), (7.0, 50), (12.0, 75), (18.0, 100))
_LIMIARES_ONDA_DIAS = ((1.0, 40), (2.0, 60), (3.0, 80), (4.0, 100))
# Score 0–100 → classe (hierárquico por limiar)
_LIMIARES_CLASSE = ((85, "roxa"), (70, "vermelha"), (50, "laranja"), (25, "amarela"), (0, "verde"))

TABLE_EMITIDA = "predicao_calor_7d_emitida_hist"
TABLE_SKILL_RESUMO = "predicao_calor_7d_skill_resumo_v1"
TABLE_SKILL_PARES = "predicao_calor_7d_skill_pares_v1"
TABLE_ML_AUX = "predicao_calor_7d_ml_aux_v1"


def _score_from_thresholds(value: float | None, limiares: tuple[tuple[float, int], ...]) -> float:
    """Mapeia valor contínuo em 0–100 pelos limiares (último limiar atingido)."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return 0.0
    v = float(value)
    score = 0
    for thr, pts in limiares:
        if v >= thr:
            score = pts
    return float(score)


def risco_termico_projetado(row: pd.Series | dict) -> dict[str, Any]:
    """Dimensão única RISCO_TÉRMICO_PROJETADO (0–100).

    Componentes (intensidade, estresse, persistência, onda) são **altamente correlacionados**.
    Para evitar dupla contagem, a composição usa o **máximo** dos quatro escores
    (regra hierárquica / “pior sinal térmico”), e não a soma nem média.
    """
    s_int = _score_from_thresholds(row.get("tmax_max_7d"), _LIMIARES_INTENSIDADE_TMAX)
    s_utci = _score_from_thresholds(row.get("utci_proxy_max_7d"), _LIMIARES_ESTRESSE_UTCI)
    s_pers = _score_from_thresholds(row.get("risco_cumulativo_3d_max_7d"), _LIMIARES_PERSISTENCIA)
    s_onda = _score_from_thresholds(row.get("dias_onda_calor_prevista_7d"), _LIMIARES_ONDA_DIAS)
    score = float(max(s_int, s_utci, s_pers, s_onda))
    nivel = "verde"
    for thr, nome in _LIMIARES_CLASSE:
        if score >= thr:
            nivel = nome
            break
    dominante = max(
        [
            ("intensidade (Tmáx)", s_int),
            ("estresse térmico (UTCI)", s_utci),
            ("persistência (risco cumulativo)", s_pers),
            ("onda de calor", s_onda),
        ],
        key=lambda t: t[1],
    )[0]
    return {
        "risco_termico_projetado_0_100": score,
        "score_intensidade": s_int,
        "score_estresse": s_utci,
        "score_persistencia": s_pers,
        "score_onda": s_onda,
        "componente_dominante": dominante,
        "nivel_predicao_7d": nivel,
        "regra_composicao": "max_componentes_termicos",
    }


def nivel_pred_from_agg(row: pd.Series | dict) -> str:
    """Classe projetada ~7d a partir do RISCO_TÉRMICO_PROJETADO (sem soma de fatores correlatos)."""
    return str(risco_termico_projetado(row)["nivel_predicao_7d"])


def documentacao_regra_projecao_md() -> str:
    """Quadro metodológico público para o boletim."""
    from sisclima.engines.boletim_el_nino.formatters import bloco_tabela, md_table

    tab = bloco_tabela(
        "Componentes do risco térmico projetado",
        md_table(
            ["Componente", "Variável", "Limiar e pontuação atribuída"],
            [
                ["Intensidade", "Tmáx máxima prevista na janela", "≥34 °C → 25 pontos; ≥37 °C → 50 pontos; ≥40 °C → 75 pontos; ≥42 °C → 100 pontos"],
                ["Estresse térmico", "UTCI máximo previsto", "≥32 °C → 25 pontos; ≥36 °C → 50 pontos; ≥40 °C → 75 pontos; ≥44 °C → 100 pontos"],
                ["Persistência", "Risco cumulativo de calor (máx. 7d)", "≥3 pontos → 25 pontos; ≥7 pontos → 50 pontos; ≥12 pontos → 75 pontos; ≥18 pontos → 100 pontos"],
                ["Onda de calor", "Dias com onda prevista no horizonte", "≥1 dia → 40 pontos; ≥2 dias → 60 pontos; ≥3 dias → 80 pontos; ≥4 dias → 100 pontos"],
            ],
        ),
        "Elaboração CIEVS-MT/ARARAS MT.",
    )
    return f"""### Como a classe projetada é calculada

A projeção operacional de aproximadamente sete dias nesta versão é uma dimensão única de **risco térmico projetado** (0–100), composta por quatro sinais do mesmo fenômeno térmico:

{tab}

**Composição (anti-redundância):** o risco térmico projetado é o máximo entre intensidade, estresse térmico, persistência e onda de calor — sem soma nem média, para evitar dupla contagem.

**Classes:** 0–24 verde; 25–49 amarela; 50–69 laranja; 70–84 vermelha; 85–100 roxa.

**Fora do cálculo da classe nesta versão:** fumaça, fogo, hidrologia e pressão assistencial (sem previsão específica no mesmo horizonte); constam como contexto concomitante.
"""


def _ibge(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "cod_ibge" in out.columns:
        out["cod_ibge"] = out["cod_ibge"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(7)
    return out


def aggregate_window(met: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Agrega tmax/UTCI/risco/onda por município em [start, end]."""
    if met is None or met.empty or "cod_ibge" not in met.columns or "data" not in met.columns:
        return pd.DataFrame()
    m = _ibge(met)
    m["data"] = pd.to_datetime(m["data"], errors="coerce").dt.normalize()
    win = m[(m["data"] >= start) & (m["data"] <= end)].copy()
    if win.empty:
        return pd.DataFrame()
    for c in ["tmax", "utci_proxy", "risco_cumulativo_3d", "onda_calor_p95_2d"]:
        if c in win.columns:
            win[c] = pd.to_numeric(win[c], errors="coerce")
    rows = []
    for cod, grp in win.groupby("cod_ibge"):
        rows.append(
            {
                "cod_ibge": str(cod),
                "tmax_max_7d": float(grp["tmax"].max()) if "tmax" in grp else np.nan,
                "utci_proxy_max_7d": float(grp["utci_proxy"].max()) if "utci_proxy" in grp else np.nan,
                "risco_cumulativo_3d_max_7d": float(grp["risco_cumulativo_3d"].max())
                if "risco_cumulativo_3d" in grp
                else np.nan,
                "dias_onda_calor_prevista_7d": float(grp["onda_calor_p95_2d"].fillna(0).sum())
                if "onda_calor_p95_2d" in grp
                else 0.0,
            }
        )
    agg = pd.DataFrame(rows)
    if agg.empty:
        return agg
    agg["nivel"] = agg.apply(nivel_pred_from_agg, axis=1)
    agg["score"] = agg["nivel"].map(STAGE_ORDER).fillna(0).astype(int)
    return agg


def archive_emission(pred: pd.DataFrame, data_emissao: pd.Timestamp | None = None) -> pd.DataFrame:
    """Anexa a emissão atual ao histórico (sem sobrescrever emissões anteriores)."""
    if pred is None or pred.empty:
        return pd.DataFrame()
    emissao = (data_emissao or pd.Timestamp.today()).normalize()
    p = _ibge(pred)
    keep = ["cod_ibge"] + [c for c in FEAT_COLS + ["nivel_predicao_7d", "risco_preditivo_score", "fonte_predicao"] if c in p.columns]
    snap = p[keep].drop_duplicates("cod_ibge").copy()
    snap["data_emissao"] = emissao.strftime("%Y-%m-%d")
    snap["horizonte_dias"] = 7
    snap["arquivado_em"] = datetime.now().isoformat(timespec="seconds")

    prev = read_table(TABLE_EMITIDA)
    if prev is not None and not prev.empty:
        prev = _ibge(prev)
        # evita duplicar mesma emissão do mesmo dia
        mask = ~(
            (prev["data_emissao"].astype(str) == snap["data_emissao"].iloc[0])
            & (prev["cod_ibge"].isin(snap["cod_ibge"]))
        )
        prev = prev.loc[mask]
        out = pd.concat([prev, snap], ignore_index=True)
    else:
        out = snap
    write_df(out, TABLE_EMITIDA)
    return snap


def _mae(a: pd.Series, b: pd.Series) -> float | None:
    x = pd.to_numeric(a, errors="coerce")
    y = pd.to_numeric(b, errors="coerce")
    ok = x.notna() & y.notna()
    if not ok.any():
        return None
    return float(np.mean(np.abs(x[ok] - y[ok])))


def _score_pairs(pred: pd.DataFrame, truth: pd.DataFrame, metodo: str, as_of: str) -> pd.DataFrame:
    if pred.empty or truth.empty:
        return pd.DataFrame()
    p = pred.rename(
        columns={
            "nivel": "nivel_previsto",
            "score": "score_previsto",
            "tmax_max_7d": "tmax_previsto",
            "utci_proxy_max_7d": "utci_previsto",
            "risco_cumulativo_3d_max_7d": "risco_previsto",
        }
    )
    t = truth.rename(
        columns={
            "nivel": "nivel_observado",
            "score": "score_observado",
            "tmax_max_7d": "tmax_observado",
            "utci_proxy_max_7d": "utci_observado",
            "risco_cumulativo_3d_max_7d": "risco_observado",
        }
    )
    m = p.merge(t, on="cod_ibge", how="inner")
    if m.empty:
        return m
    m["acerto_exato"] = (m["nivel_previsto"] == m["nivel_observado"]).astype(int)
    m["acerto_tol1"] = (np.abs(m["score_previsto"] - m["score_observado"]) <= 1).astype(int)
    m["metodo"] = metodo
    m["as_of"] = as_of
    return m


def evaluate_persistence_skill(met: pd.DataFrame, max_as_of: int = 14) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Backtest de persistência: pred=[D-6..D], truth=[D+1..D+7]."""
    if met is None or met.empty or "data" not in met.columns:
        return pd.DataFrame(), pd.DataFrame()
    m = _ibge(met)
    m["data"] = pd.to_datetime(m["data"], errors="coerce").dt.normalize()
    dates = sorted(m["data"].dropna().unique())
    if len(dates) < 14:
        return pd.DataFrame(), pd.DataFrame()

    # candidatos a D: precisam de D+7 e D-6
    candidates = []
    date_set = set(pd.Timestamp(d).normalize() for d in dates)
    for d in dates:
        d = pd.Timestamp(d).normalize()
        if (d + pd.Timedelta(days=7)) in date_set and (d - pd.Timedelta(days=6)) in date_set:
            candidates.append(d)
    if not candidates:
        # relax: usa min/max contínuos mesmo com buracos
        for d in dates:
            d = pd.Timestamp(d).normalize()
            if d + pd.Timedelta(days=7) <= pd.Timestamp(dates[-1]) and d - pd.Timedelta(days=6) >= pd.Timestamp(dates[0]):
                candidates.append(d)
    candidates = candidates[-max_as_of:]
    pares_list = []
    for d in candidates:
        pred = aggregate_window(m, d - pd.Timedelta(days=6), d)
        truth = aggregate_window(m, d + pd.Timedelta(days=1), d + pd.Timedelta(days=7))
        pares_list.append(_score_pairs(pred, truth, "persistencia_7d", d.strftime("%Y-%m-%d")))
    pares = pd.concat([p for p in pares_list if p is not None and not p.empty], ignore_index=True) if pares_list else pd.DataFrame()
    resumo = _summarize_pares(pares, "persistencia_7d")
    return resumo, pares


def evaluate_archived_skill(met: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compara emissões arquivadas com a janela realizada em met_biometeo."""
    hist = read_table(TABLE_EMITIDA)
    if hist is None or hist.empty or met is None or met.empty:
        return pd.DataFrame(), pd.DataFrame()
    hist = _ibge(hist)
    hist["data_emissao"] = pd.to_datetime(hist["data_emissao"], errors="coerce").dt.normalize()
    today = pd.Timestamp.today().normalize()
    mature = hist[hist["data_emissao"] <= today - pd.Timedelta(days=7)].copy()
    if mature.empty:
        return pd.DataFrame(), pd.DataFrame()

    pares_list = []
    for emissao, grp in mature.groupby("data_emissao"):
        truth = aggregate_window(met, emissao, emissao + pd.Timedelta(days=7))
        if truth.empty:
            continue
        pred = grp.rename(
            columns={
                "nivel_predicao_7d": "nivel",
                "risco_preditivo_score": "score",
            }
        )
        if "nivel" not in pred.columns:
            pred["nivel"] = pred.apply(nivel_pred_from_agg, axis=1)
        if "score" not in pred.columns:
            pred["score"] = pred["nivel"].map(STAGE_ORDER).fillna(0).astype(int)
        pares_list.append(
            _score_pairs(
                pred[["cod_ibge", "nivel", "score", "tmax_max_7d", "utci_proxy_max_7d", "risco_cumulativo_3d_max_7d"]],
                truth,
                "emissao_arquivada",
                pd.Timestamp(emissao).strftime("%Y-%m-%d"),
            )
        )
    pares = pd.concat([p for p in pares_list if p is not None and not p.empty], ignore_index=True) if pares_list else pd.DataFrame()
    resumo = _summarize_pares(pares, "emissao_arquivada")
    return resumo, pares


def _summarize_pares(pares: pd.DataFrame, metodo: str) -> pd.DataFrame:
    if pares is None or pares.empty:
        return pd.DataFrame(
            [
                {
                    "metodo": metodo,
                    "n_pares": 0,
                    "hit_rate_exato": None,
                    "hit_rate_tol1": None,
                    "mae_tmax": None,
                    "mae_utci": None,
                    "avaliado_em": datetime.now().isoformat(timespec="seconds"),
                }
            ]
        )
    row = {
        "metodo": metodo,
        "n_pares": int(len(pares)),
        "n_as_of": int(pares["as_of"].nunique()) if "as_of" in pares.columns else 1,
        "hit_rate_exato": float(pares["acerto_exato"].mean()),
        "hit_rate_tol1": float(pares["acerto_tol1"].mean()),
        "mae_tmax": _mae(pares.get("tmax_previsto"), pares.get("tmax_observado")),
        "mae_utci": _mae(pares.get("utci_previsto"), pares.get("utci_observado")),
        "avaliado_em": datetime.now().isoformat(timespec="seconds"),
    }
    return pd.DataFrame([row])


def _heuristic_probs(row: pd.Series) -> dict[str, float]:
    """Probabilidades suaves a partir da distância aos limiares (auditável, sem caixa-preta)."""
    scores = {lv: 0.15 for lv in LEVELS_PRED}
    t = pd.to_numeric(row.get("tmax_max_7d"), errors="coerce")
    u = pd.to_numeric(row.get("utci_proxy_max_7d"), errors="coerce")
    r = pd.to_numeric(row.get("risco_cumulativo_3d_max_7d"), errors="coerce")
    base = nivel_pred_from_agg(row)
    scores[base] = scores.get(base, 0.15) + 0.45
    if pd.notna(t):
        if t >= 39:
            scores["vermelha"] += 0.2
            scores["roxa"] += 0.1
        elif t >= 36:
            scores["laranja"] += 0.2
        elif t >= 33:
            scores["amarela"] += 0.15
        else:
            scores["verde"] += 0.2
    if pd.notna(u):
        if u >= 42:
            scores["roxa"] += 0.2
        elif u >= 38:
            scores["vermelha"] += 0.15
        elif u >= 34:
            scores["laranja"] += 0.15
    if pd.notna(r):
        if r >= 15:
            scores["roxa"] += 0.15
        elif r >= 10:
            scores["vermelha"] += 0.15
        elif r >= 5:
            scores["laranja"] += 0.1
    total = sum(scores.values()) or 1.0
    return {k: float(v / total) for k, v in scores.items()}


def attach_ml_aux(pred: pd.DataFrame, pares_treino: pd.DataFrame | None = None) -> pd.DataFrame:
    """Anexa probabilidades auxiliares; nunca altera `nivel_predicao_7d`."""
    if pred is None or pred.empty:
        return pred
    out = pred.copy()
    use_sklearn = False
    model = None
    classes = LEVELS_PRED

    if pares_treino is not None and len(pares_treino) >= 80:
        try:
            from sklearn.linear_model import LogisticRegression
            from sklearn.preprocessing import StandardScaler

            feat_map = {
                "tmax_max_7d": "tmax_previsto",
                "utci_proxy_max_7d": "utci_previsto",
                "risco_cumulativo_3d_max_7d": "risco_previsto",
            }
            X_cols_src = [feat_map[c] for c in FEAT_COLS[:3] if feat_map[c] in pares_treino.columns]
            if len(X_cols_src) >= 2 and "nivel_observado" in pares_treino.columns:
                train = pares_treino.dropna(subset=X_cols_src + ["nivel_observado"]).copy()
                train = train[train["nivel_observado"].isin(LEVELS_PRED)]
                if len(train) >= 80 and train["nivel_observado"].nunique() >= 2:
                    X = train[X_cols_src].astype(float).values
                    y = train["nivel_observado"].astype(str).values
                    scaler = StandardScaler()
                    Xs = scaler.fit_transform(X)
                    model = LogisticRegression(max_iter=400)
                    model.fit(Xs, y)
                    classes = list(model.classes_)
                    use_sklearn = True
                    # pred features
                    Xp = out[[c for c in FEAT_COLS[:3]]].copy()
                    for c in FEAT_COLS[:3]:
                        if c not in Xp.columns:
                            Xp[c] = np.nan
                    Xp = Xp[FEAT_COLS[:3]].astype(float).fillna(Xp.median(numeric_only=True))
                    probs = model.predict_proba(scaler.transform(Xp.values))
                    for i, cls in enumerate(classes):
                        out[f"p_{cls}"] = probs[:, i]
                    out["ml_nivel_sugerido"] = [classes[int(i)] for i in np.argmax(probs, axis=1)]
                    out["ml_confianca"] = probs.max(axis=1)
                    out["ml_metodo"] = "logistic_sklearn"
        except Exception as exc:  # noqa: BLE001
            log.warning("ML auxiliar sklearn indisponível (%s) — usando heurística.", exc)
            use_sklearn = False

    if not use_sklearn:
        rows = out.apply(_heuristic_probs, axis=1)
        for lv in LEVELS_PRED:
            out[f"p_{lv}"] = rows.map(lambda d, k=lv: d.get(k, 0.0))
        prob_cols = [f"p_{lv}" for lv in LEVELS_PRED]
        out["ml_nivel_sugerido"] = out[prob_cols].idxmax(axis=1).str.replace("^p_", "", regex=True)
        out["ml_confianca"] = out[prob_cols].max(axis=1)
        out["ml_metodo"] = "heuristica_limiares"

    out["p_laranja_plus"] = out[[f"p_{lv}" for lv in ("laranja", "vermelha", "roxa") if f"p_{lv}" in out.columns]].sum(axis=1)
    out["p_vermelha_plus"] = out[[f"p_{lv}" for lv in ("vermelha", "roxa") if f"p_{lv}" in out.columns]].sum(axis=1)
    out["ml_nota"] = "Camada auxiliar — o nível SES permanece o da regra (`nivel_predicao_7d`)."
    return out


def run_predicao_skill(met: pd.DataFrame, pred: pd.DataFrame) -> dict[str, Any]:
    """Arquiva emissão, avalia skill e grava ML auxiliar. Retorna resumo para o enrichment."""
    summary: dict[str, Any] = {"ok": True}
    try:
        archived = archive_emission(pred)
        summary["emitidas"] = int(len(archived))
    except Exception as exc:  # noqa: BLE001
        log.warning("Arquivo de emissão 7d falhou: %s", exc)
        summary["emitidas"] = 0
        summary["archive_error"] = str(exc)

    resumos = []
    pares_all = []
    try:
        r1, p1 = evaluate_persistence_skill(met)
        if not r1.empty:
            resumos.append(r1)
        if not p1.empty:
            pares_all.append(p1)
    except Exception as exc:  # noqa: BLE001
        log.warning("Skill persistência falhou: %s", exc)
        summary["persistencia_error"] = str(exc)

    try:
        r2, p2 = evaluate_archived_skill(met)
        if not r2.empty:
            resumos.append(r2)
        if not p2.empty:
            pares_all.append(p2)
    except Exception as exc:  # noqa: BLE001
        log.warning("Skill arquivo falhou: %s", exc)
        summary["arquivo_error"] = str(exc)

    resumo = pd.concat(resumos, ignore_index=True) if resumos else pd.DataFrame()
    pares = pd.concat(pares_all, ignore_index=True) if pares_all else pd.DataFrame()
    write_df(resumo if not resumo.empty else pd.DataFrame(), TABLE_SKILL_RESUMO)
    # guarda amostra recente de pares (limite operacional)
    if not pares.empty and len(pares) > 8000:
        pares = pares.tail(8000)
    write_df(pares if not pares.empty else pd.DataFrame(), TABLE_SKILL_PARES)

    pred_ml = attach_ml_aux(pred, pares if not pares.empty else None)
    ml_cols = [
        c
        for c in pred_ml.columns
        if c == "cod_ibge"
        or c.startswith("p_")
        or c.startswith("ml_")
    ]
    write_df(pred_ml[ml_cols].drop_duplicates("cod_ibge") if "cod_ibge" in pred_ml.columns else pred_ml, TABLE_ML_AUX)

    # regrava pred municipal com probs auxiliares (nível regra intacto)
    if not pred.empty and not pred_ml.empty:
        base_cols = [c for c in pred.columns]
        extra = [c for c in pred_ml.columns if c not in base_cols or c.startswith("p_") or c.startswith("ml_")]
        merged = pred.drop(columns=[c for c in extra if c in pred.columns], errors="ignore")
        merged = merged.merge(pred_ml[["cod_ibge"] + [c for c in extra if c != "cod_ibge"]], on="cod_ibge", how="left")
        # garante que nivel da regra não foi trocado
        if "nivel_predicao_7d" in pred.columns:
            merged["nivel_predicao_7d"] = pred["nivel_predicao_7d"].values
        write_df(merged, "predicao_calor_7d_municipal_v6")

    if not resumo.empty:
        summary["skill"] = resumo.to_dict(orient="records")
    summary["n_pares"] = int(len(pares))
    summary["ml_metodo"] = str(pred_ml["ml_metodo"].iloc[0]) if not pred_ml.empty and "ml_metodo" in pred_ml.columns else None
    return summary
