from __future__ import annotations

from pathlib import Path
import pandas as pd

from sisclima.core.config import APP_CONFIG
from sisclima.core.db import read_table
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)


def _safe_read(table: str) -> pd.DataFrame:
    try:
        df = read_table(table)
        return df if df is not None else pd.DataFrame()
    except Exception as exc:
        log.warning("Falha ao ler tabela %s para exportação pública: %s", table, exc)
        return pd.DataFrame()


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if df is None:
        df = pd.DataFrame()
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _prefer_column(df: pd.DataFrame, options: list[str]) -> str | None:
    for c in options:
        if c in df.columns:
            return c
    return None


def _build_predicao_7d(resumo: pd.DataFrame, met: pd.DataFrame) -> pd.DataFrame:
    if met is not None and not met.empty:
        out = met.copy()
        if "data" in out.columns:
            out["data"] = pd.to_datetime(out["data"], errors="coerce")
            out = out.sort_values("data")
            out = out.groupby("municipio", as_index=False).tail(7) if "municipio" in out.columns else out.tail(200)
            out["data"] = out["data"].dt.date.astype(str)
        keep = [c for c in ["data", "cod_ibge", "municipio", "tmax", "tmin", "heat_index", "utci_proxy", "risco_cumulativo_3d"] if c in out.columns]
        return out[keep] if keep else out

    if resumo is None or resumo.empty:
        return pd.DataFrame()
    keep = [c for c in ["data_referencia", "cod_ibge", "municipio", "tmax", "utci_proxy", "risco_cumulativo_3d", "nivel", "score"] if c in resumo.columns]
    out = resumo[keep].copy() if keep else resumo.copy()
    if "data_referencia" in out.columns:
        out = out.rename(columns={"data_referencia": "data"})
    return out


def _build_alerta_inteligente(resumo: pd.DataFrame) -> pd.DataFrame:
    if resumo is None or resumo.empty:
        return pd.DataFrame()
    out = resumo.copy()
    keep = [c for c in [
        "data_referencia",
        "cod_ibge",
        "municipio",
        "nivel",
        "score",
        "tmax",
        "utci_proxy",
        "risco_cumulativo_3d",
        "pressao_calor_pct",
        "ocupacao_leitos_pct",
        "iq_ar_score",
        "qualidade_ar_nivel",
        "indice_resiliencia",
        "motivo",
    ] if c in out.columns]
    out = out[keep] if keep else out
    if "score" in out.columns:
        out["prioridade"] = pd.to_numeric(out["score"], errors="coerce").fillna(0).astype(int)
    if "nivel" in out.columns:
        out["alerta_ativo"] = out["nivel"].astype(str).str.lower().isin(["amarela", "laranja", "vermelha", "roxa"])
    return out


def _build_priorizacao_epidemiologica(resumo: pd.DataFrame) -> pd.DataFrame:
    if resumo is None or resumo.empty:
        return pd.DataFrame()
    out = resumo.copy()
    keep = [c for c in [
        "cod_ibge",
        "municipio",
        "nivel",
        "score",
        "pressao_calor_pct",
        "casos_srag",
        "positividade_lacen_pct",
        "notificacoes_sinan",
        "obitos_total",
        "obitos_calor_suspeitos",
        "indice_vulnerabilidade_calor",
        "indice_resiliencia",
        "motivo",
    ] if c in out.columns]
    out = out[keep] if keep else out
    if "score" in out.columns:
        out = out.sort_values("score", ascending=False)
    return out


def _build_ocupacao_hospitalar(resumo: pd.DataFrame, ocupacao_raw: pd.DataFrame) -> pd.DataFrame:
    if ocupacao_raw is not None and not ocupacao_raw.empty:
        return ocupacao_raw.copy()
    if resumo is None or resumo.empty:
        return pd.DataFrame()
    keep = [c for c in [
        "data_referencia",
        "cod_ibge",
        "municipio",
        "ocupacao_leitos_pct",
        "leitos_total",
        "leitos_sus",
        "leitos_ocupados",
        "leitos_livres",
        "leitos_bloqueados_movimento",
        "leitos_higienizacao",
        "leitos_reservados",
        "ultima_movimentacao_ocupacao",
        "fonte_ocupacao",
    ] if c in resumo.columns]
    out = resumo[keep].copy() if keep else resumo.copy()
    if "data_referencia" in out.columns:
        out = out.rename(columns={"data_referencia": "data"})
    return out


def _build_ops_resumo(resumo: pd.DataFrame, ops_raw: pd.DataFrame) -> pd.DataFrame:
    if ops_raw is not None and not ops_raw.empty:
        return ops_raw.copy()
    return resumo.copy() if resumo is not None else pd.DataFrame()


def _build_status_alertas(resumo: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if resumo is None or resumo.empty:
        empty = pd.DataFrame()
        return empty, empty, empty, empty

    out = resumo.copy()
    municipio_col = _prefer_column(out, ["municipio"])
    nivel_col = _prefer_column(out, ["nivel"])
    score_col = _prefer_column(out, ["score"])
    reg_col = _prefer_column(out, ["regional_saude", "regional", "regiao_saude"])
    data_col = _prefer_column(out, ["data_referencia", "data"])

    for col in [municipio_col, nivel_col, score_col, reg_col, data_col]:
        if col and col not in out.columns:
            col = None

    if score_col is None and nivel_col:
        score_map = {"verde": 0, "amarela": 1, "laranja": 2, "vermelha": 3, "roxa": 4}
        out["_score_proxy"] = out[nivel_col].astype(str).str.lower().map(score_map).fillna(0)
        score_col = "_score_proxy"

    if reg_col is None:
        out["_regional_fallback"] = "Sem regional informada"
        reg_col = "_regional_fallback"

    score_series = pd.to_numeric(out[score_col], errors="coerce") if score_col else pd.Series([0] * len(out))
    alerta_df = out[score_series >= 2].copy()

    nivel_estado = "cinza"
    if nivel_col and not out[nivel_col].dropna().empty:
        score_level = {"cinza": 0, "verde": 1, "amarela": 2, "laranja": 3, "vermelha": 4, "roxa": 5}
        nivel_estado = max(out[nivel_col].astype(str).str.lower().tolist(), key=lambda x: score_level.get(x, 0))
    data_ref = str(out[data_col].dropna().iloc[-1]) if data_col and not out[data_col].dropna().empty else ""

    status = pd.DataFrame([{
        "data_referencia": data_ref,
        "nivel_estadual": nivel_estado,
        "municipios_monitorados": int(len(out)),
        "municipios_alerta": int(len(alerta_df)),
        "email_enviado": False,
        "telegram_enviado": False,
        "webhook_enviado": False,
        "origem": "pipeline_sqlite_export",
    }])

    estado = pd.DataFrame([{
        "data_referencia": data_ref,
        "nivel_estadual": nivel_estado,
        "municipios_em_alerta": int(len(alerta_df)),
    }])

    if alerta_df.empty:
        regionais = pd.DataFrame(columns=["data_referencia", "regional_saude", "municipios_em_alerta"])
    else:
        regionais = (
            alerta_df.groupby(reg_col, dropna=False)[reg_col]
            .count()
            .reset_index(name="municipios_em_alerta")
            .rename(columns={reg_col: "regional_saude"})
        )
        regionais["data_referencia"] = data_ref

    cuiaba = pd.DataFrame(columns=list(alerta_df.columns))
    if municipio_col and not alerta_df.empty:
        cuiaba = alerta_df[alerta_df[municipio_col].astype(str).str.lower().eq("cuiabá") | alerta_df[municipio_col].astype(str).str.lower().eq("cuiaba")].copy()

    return status, estado, regionais, cuiaba


def export_public_data() -> dict[str, int]:
    """Exporta as principais saídas do SQLite para data/public em formato CSV."""
    public_dir = APP_CONFIG.root / "data" / "public"
    public_dir.mkdir(parents=True, exist_ok=True)

    resumo = _safe_read("resumo_municipal_atual")
    met = _safe_read("met_biometeo")
    aq = _safe_read("qualidade_ar_municipal")
    ocup = _safe_read("hospital_ocupacao_municipio")
    ops = _safe_read("ops_resumo_operacional_cnes")

    pred = _build_predicao_7d(resumo, met)
    alerta = _build_alerta_inteligente(resumo)
    prior = _build_priorizacao_epidemiologica(resumo)
    ocup_out = _build_ocupacao_hospitalar(resumo, ocup)
    ops_out = _build_ops_resumo(resumo, ops)
    status, estado, regionais, cuiaba = _build_status_alertas(resumo)

    exports: dict[str, pd.DataFrame] = {
        "resumo_municipal_atual.csv": resumo,
        "predicao_calor_7d_municipal_v6.csv": pred,
        "alerta_inteligente_municipal_v6.csv": alerta,
        "v9_priorizacao_epidemiologica.csv": prior,
        "qualidade_ar_municipal.csv": aq,
        "hospital_ocupacao_municipio.csv": ocup_out,
        "ops_resumo_operacional_cnes.csv": ops_out,
        "status_alertas_vigia.csv": status,
        "alertas_estado_vigia.csv": estado,
        "alertas_regionais_vigia.csv": regionais,
        "alerta_cuiaba_vigia.csv": cuiaba,
    }

    out_counts: dict[str, int] = {}
    for filename, frame in exports.items():
        target = public_dir / filename
        _write_csv(frame, target)
        out_counts[filename] = int(len(frame))

    return out_counts
