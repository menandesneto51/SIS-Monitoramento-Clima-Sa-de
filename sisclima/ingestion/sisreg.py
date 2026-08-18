# -*- coding: utf-8 -*-
"""
Ingestão SISREG → ops_sisreg_municipio.

Credenciais: SISREG_HOST / PORT / DATABASE / USER / PASSWORD (ver .env).
Views oficiais (mesmo contrato do projeto Monitoramento ondas de calor V16):
  - dbo.VW_AMBULATORIAL_SOLICITACAO
  - dbo.VW_HOSPITALAR_SINTETICO

Fallback: CSV municipal já gerado no projeto V16 (142 municípios).
"""
from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from sisclima.core.config import ROOT
from sisclima.core.db import write_df

_ONDAS_V16_DATA = Path(
    r"C:\Users\Menandesneto\OneDrive\CIEVS MT"
    r"\Monitoramento ondas de calor\v16_integrada_el_nino_saude\data"
)

DEFAULT_CSV_CANDIDATES = [
    # Preferir extratos V16 com fila/pendências reais (SQL Server SES).
    _ONDAS_V16_DATA / "sisreg_pressao_regulatoria_atual_municipal_v16_2_4_3_1_padronizada.csv",
    _ONDAS_V16_DATA / "sisreg_pressao_regulatoria_atual_municipal_v16_2_4_3.csv",
    _ONDAS_V16_DATA / "sisreg_pressao_regulatoria_atual_municipal_v16_2.csv",
    _ONDAS_V16_DATA / "base_integrada_municipal_v16_1_2_sim_sisreg_real.csv",
    # Espelho local — só usar se tiver variância (evita CSV zerado que achata o índice).
    ROOT / "data" / "sisreg" / "ops_sisreg_municipio.csv",
]


def _load_dotenv_keys(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def sisreg_config() -> dict[str, Any]:
    for p in (ROOT / ".env", Path(r"C:\Users\Menandesneto\OneDrive\CIEVS MT\Monitoramento ondas de calor\.env")):
        _load_dotenv_keys(p)
    host = os.getenv("SISREG_HOST") or os.getenv("SISREG_SQLSERVER")
    port = (os.getenv("SISREG_PORT") or "").strip()
    database = os.getenv("SISREG_DATABASE", "SES")
    user = os.getenv("SISREG_USER") or os.getenv("SISREG_USERNAME")
    password = os.getenv("SISREG_PASSWORD")
    schema = os.getenv("SISREG_SCHEMA", "dbo")
    if not host:
        raise ValueError("SISREG_HOST não configurado no .env")
    servidor = f"{host},{port}" if port and "," not in host else host
    return {
        "servidor": servidor,
        "banco": database,
        "usuario": user,
        "senha": password,
        "schema": schema,
        "host": host,
        "porta": port or "1433",
    }


def _pick_driver() -> str:
    import pyodbc

    installed = pyodbc.drivers()
    for d in (
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server Native Client 11.0",
        "SQL Server",
    ):
        if d in installed:
            return d
    raise RuntimeError(f"Nenhum driver SQL Server. Instalados: {installed}")


def connect_sisreg():
    import pyodbc

    cfg = sisreg_config()
    driver = _pick_driver()
    parts = [
        f"DRIVER={{{driver}}}",
        f"SERVER={cfg['servidor']}",
        f"DATABASE={cfg['banco']}",
        "Encrypt=yes",
        "TrustServerCertificate=yes",
        "Connection Timeout=20",
    ]
    if cfg["usuario"] and cfg["senha"]:
        parts.extend([f"UID={cfg['usuario']}", f"PWD={cfg['senha']}"])
    else:
        parts.append("Trusted_Connection=yes")
    conn = pyodbc.connect(";".join(parts), autocommit=True)
    conn.timeout = 600
    return conn, driver, cfg


def _norm_mun(valor: Any) -> str:
    if pd.isna(valor):
        return ""
    texto = str(valor).strip().upper()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^A-Z0-9]+", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    texto = re.sub(r"^MUNICIPIO DE\s+", "", texto)
    texto = re.sub(r"\s+MATO GROSSO$", "", texto)
    texto = re.sub(r"\s+MT$", "", texto)
    return texto.strip()


def _query_pendentes_por_territorio(conn, schema: str, view: str, mun_col: str, status_col: str, data_col: str) -> pd.DataFrame:
    """Agrega fila/pendências operacionais por município de residência (status canônicos V16)."""
    # Status alinhados ao dicionário operacional do projeto ondas de calor / SISREG SES.
    if "AMBULATORIAL" in view.upper():
        status_filter = f"""
          (
                UPPER(CONVERT(nvarchar(200), {status_col})) LIKE N'%PENDENTE%FILA DE ESPERA%'
             OR UPPER(CONVERT(nvarchar(200), {status_col})) LIKE N'%PENDENTE%REGULADOR%'
             OR UPPER(CONVERT(nvarchar(200), {status_col})) LIKE N'%AGENDADA%FILA DE ESPERA%'
             OR UPPER(CONVERT(nvarchar(200), {status_col})) LIKE N'%PENDENTE CONFIRMA%'
          )
        """
    else:
        status_filter = f"""
          (
                UPPER(LTRIM(RTRIM(CONVERT(nvarchar(200), {status_col})))) = N'PENDENTE'
             OR UPPER(CONVERT(nvarchar(200), {status_col})) LIKE N'PENDENTE%'
          )
        """
    sql = f"""
    SELECT
        COALESCE(NULLIF(LTRIM(RTRIM(CONVERT(nvarchar(300), {mun_col}))), N''), N'SEM_INFORMACAO') AS territorio,
        COUNT_BIG(*) AS solicitacoes_abertas,
        AVG(CONVERT(float, DATEDIFF(HOUR, TRY_CONVERT(datetime2, {data_col}), SYSDATETIME()))) AS fila_media_h,
        MAX(CONVERT(float, DATEDIFF(HOUR, TRY_CONVERT(datetime2, {data_col}), SYSDATETIME()))) AS tempo_espera_max_h
    FROM [{schema}].[{view}]
    WHERE TRY_CONVERT(datetime2, {data_col}) IS NOT NULL
      AND TRY_CONVERT(datetime2, {data_col}) >= DATEADD(DAY, -365, SYSDATETIME())
      AND {status_filter}
    GROUP BY COALESCE(NULLIF(LTRIM(RTRIM(CONVERT(nvarchar(300), {mun_col}))), N''), N'SEM_INFORMACAO')
    """
    return pd.read_sql(sql, conn)


def fetch_sisreg_live() -> pd.DataFrame:
    """Tenta extrair pressão atual das views SISREG (rede SES/VPN)."""
    conn, driver, cfg = connect_sisreg()
    try:
        frames = []
        attempts = [
            ("VW_AMBULATORIAL_SOLICITACAO", "municipio_paciente_residencia", "status_solicitacao", "data_solicitacao"),
            ("VW_HOSPITALAR_SINTETICO", "municipio_paciente_residencia", "status", "data_solicitacao"),
        ]
        for view, mun, status, data in attempts:
            try:
                part = _query_pendentes_por_territorio(conn, cfg["schema"], view, mun, status, data)
                part["fonte_view"] = view
                frames.append(part)
            except Exception as exc:  # noqa: BLE001
                frames.append(pd.DataFrame({"territorio": [], "erro": [str(exc)], "fonte_view": [view]}))
        if not frames:
            return pd.DataFrame()
        raw = pd.concat([f for f in frames if "solicitacoes_abertas" in f.columns], ignore_index=True)
        if raw.empty:
            raise RuntimeError("Views SISREG acessíveis, mas sem linhas de fila/pendência.")
        raw["territorio_norm"] = raw["territorio"].map(_norm_mun)
        g = (
            raw.groupby("territorio_norm", as_index=False)
            .agg(
                solicitacoes_abertas=("solicitacoes_abertas", "sum"),
                fila_media_h=("fila_media_h", "mean"),
                tempo_espera_max_h=("tempo_espera_max_h", "max"),
            )
        )
        g["fonte"] = f"SISREG_LIVE:{cfg['host']}"
        g["data_referencia"] = datetime.now().date().isoformat()
        g["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
        return g
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _csv_has_signal(path: Path) -> bool:
    """True se o CSV tem métricas SISREG com alguma variância (não só zeros)."""
    try:
        probe = pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig", nrows=400)
    except Exception:
        return False
    if "cod_ibge" not in probe.columns:
        return False
    signal_cols = [
        "solicitacoes_abertas",
        "amb_fila_espera_total",
        "amb_fila_ativa_estrita_total",
        "amb_fila_ativa_estrita_365d",
        "hosp_pendentes_total",
        "hosp_pendentes_365d",
        "hosp_pendentes_recentes_ate365d",
        "fila_media_h",
        "amb_tempo_espera_medio_dias",
    ]
    for col in signal_cols:
        if col not in probe.columns:
            continue
        s = pd.to_numeric(probe[col], errors="coerce")
        if s.notna().any() and float(s.fillna(0).abs().sum()) > 0 and int(s.nunique(dropna=True)) > 1:
            return True
    return False


def load_sisreg_csv(path: Path | None = None) -> pd.DataFrame:
    """Converte CSV V16 (já mapeado por IBGE) para o contrato ops_sisreg_municipio."""
    candidates = [path] if path else DEFAULT_CSV_CANDIDATES
    chosen = None
    for c in candidates:
        if not c or not Path(c).exists():
            continue
        p = Path(c)
        # Não aceitar espelho local zerado se houver candidato V16 com sinal.
        if p.name == "ops_sisreg_municipio.csv" and not _csv_has_signal(p):
            continue
        if p.name.startswith("sisreg_pressao") or "sisreg" in p.name.lower() or "sim_sisreg" in p.name.lower():
            if not _csv_has_signal(p) and p.suffix.lower() == ".csv":
                # ainda assim preferir V16 bruto se tiver colunas amb_/hosp_
                try:
                    head = pd.read_csv(p, sep=None, engine="python", encoding="utf-8-sig", nrows=2)
                    if not any(str(c).startswith(("amb_", "hosp_")) for c in head.columns):
                        continue
                except Exception:
                    continue
        chosen = p
        break
    if chosen is None:
        # último recurso: qualquer candidato existente
        for c in candidates:
            if c and Path(c).exists():
                chosen = Path(c)
                break
    if chosen is None:
        raise FileNotFoundError("Nenhum CSV SISREG encontrado nos caminhos padrão.")

    df = pd.read_csv(chosen, sep=None, engine="python", encoding="utf-8-sig")
    if "cod_ibge" not in df.columns:
        raise ValueError(f"CSV sem cod_ibge: {chosen}")

    out = pd.DataFrame()
    out["cod_ibge"] = df["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
    out["municipio"] = df["municipio"] if "municipio" in df.columns else None
    out["regional_saude"] = df["regional_saude"] if "regional_saude" in df.columns else None

    def _num_col(*names: str) -> pd.Series:
        for name in names:
            if name not in df.columns:
                continue
            series = pd.to_numeric(df[name], errors="coerce")
            if isinstance(series, pd.Series) and not series.isna().all():
                return series
        return pd.Series(float("nan"), index=df.index, dtype="float64")

    # Preferir fluxo recente (7d) — alinhado aos limiares live (50/300).
    # Estoque histórico (fila_ativa total / pendentes totais) satura o semáforo.
    flow_amb = _num_col("amb_solicitacoes_7d")
    flow_hosp = _num_col("hosp_solicitacoes_7d")
    if flow_amb.notna().any() or flow_hosp.notna().any():
        out["solicitacoes_abertas"] = (flow_amb.fillna(0) + flow_hosp.fillna(0)).round(0)
    else:
        amb = _num_col(
            "amb_fila_ativa_estrita_365d",
            "amb_aguardando_regulacao_total",
            "amb_fila_ativa_estrita_total",
            "amb_fila_espera_total",
            "solicitacoes_abertas",
        )
        hosp = _num_col(
            "hosp_pendentes_365d",
            "hosp_pendentes_recentes_ate365d",
            "hosp_pendentes_total",
        )
        out["solicitacoes_abertas"] = (amb.fillna(0) + hosp.fillna(0)).round(0)

    # CSV V16: não usar tempo médio de estoque (mesmo "recente_*") — valores em
    # centenas de dias satura limiares pensados para fila live em horas.
    # O pilar SISREG no fallback CSV fica nas solicitações/fluxo 7d.
    out["fila_media_h"] = pd.Series(float("nan"), index=df.index, dtype="float64")
    out["tempo_espera_h"] = out["fila_media_h"]

    # Taxa de regulação aproximada (autorizadas / solicitações) quando disponível
    auth = _num_col("amb_autorizadas_total")
    sol30 = _num_col("amb_solicitacoes_30d")
    denom = sol30.where(sol30 > 0)
    taxa = (100.0 * auth / denom).replace([float("inf"), float("-inf")], pd.NA)
    taxa = pd.to_numeric(taxa, errors="coerce").clip(0, 100)
    out["taxa_regulacao_pct"] = taxa.round(1)

    out["fonte"] = f"SISREG_CSV:{chosen.name}"
    # data de referência mais recente disponível no arquivo
    for col in (
        "data_referencia_sisreg_v16_2_4_3",
        "data_referencia_sisreg_v16_2_1",
        "data_referencia_sisreg_v16_2",
        "data_padronizacao_semantica_v16_2_4_3_1",
    ):
        if col in df.columns and df[col].notna().any():
            out["data_referencia"] = pd.to_datetime(df[col], errors="coerce").dt.date.astype(str)
            break
    else:
        out["data_referencia"] = datetime.now().date().isoformat()
    out["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
    out["arquivo_origem"] = str(chosen)
    return out.dropna(subset=["cod_ibge"]).drop_duplicates("cod_ibge")


def _municipios_para_mapa(mun: pd.DataFrame | None = None) -> pd.DataFrame:
    """Catálogo com nomes IBGE reais — não usar resumo (pode estar todo 'Cuiabá')."""
    from sisclima.ingestion.ibge_municipios import catalogo_municipios_mt

    cat = catalogo_municipios_mt()
    if cat is not None and not cat.empty:
        return cat
    if mun is not None and not mun.empty and "municipio" in mun.columns:
        n = mun["municipio"].dropna().astype(str).str.strip().nunique()
        if n >= 50:
            return mun
    return mun if mun is not None else pd.DataFrame()


def map_live_to_ibge(live: pd.DataFrame, municipios: pd.DataFrame) -> pd.DataFrame:
    """Mapeia território textual → cod_ibge via nome normalizado (só MT)."""
    mun = _municipios_para_mapa(municipios)
    if mun is None or mun.empty or "municipio" not in mun.columns:
        return pd.DataFrame()
    mun = mun.copy()
    mun["cod_ibge"] = mun["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
    mun["municipio_norm"] = mun["municipio"].map(_norm_mun)
    mun = mun[mun["municipio_norm"].astype(str).str.len() > 0]
    mapa = dict(zip(mun["municipio_norm"], mun["cod_ibge"]))
    nomes = dict(zip(mun["municipio_norm"], mun["municipio"]))
    live = live.copy()
    live["cod_ibge"] = live["territorio_norm"].map(mapa)
    live["municipio"] = live["territorio_norm"].map(nomes)
    if "regional_saude" in mun.columns:
        live["regional_saude"] = live["territorio_norm"].map(
            dict(zip(mun["municipio_norm"], mun["regional_saude"]))
        )
    live["tempo_espera_h"] = live.get("fila_media_h")
    out = live.dropna(subset=["cod_ibge"])
    return out[out["cod_ibge"].astype(str).str.startswith("51")]


def persist_ops_sisreg(df: pd.DataFrame) -> int:
    cols = [
        "cod_ibge",
        "municipio",
        "regional_saude",
        "data_referencia",
        "fila_media_h",
        "tempo_espera_h",
        "solicitacoes_abertas",
        "taxa_regulacao_pct",
        "fonte",
        "atualizado_em",
    ]
    out = df[[c for c in cols if c in df.columns]].copy()
    write_df(out, "ops_sisreg_municipio", if_exists="replace")
    # espelho CSV local
    dest = ROOT / "data" / "sisreg" / "ops_sisreg_municipio.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(dest, index=False, encoding="utf-8-sig")
    return len(out)


def atualizar_sisreg(*, prefer_live: bool = True, csv_path: Path | None = None) -> dict[str, Any]:
    """
    Fluxo:
      1) tenta live (VPN/rede SES)
      2) se falhar, importa CSV V16
    """
    meta: dict[str, Any] = {"ok": False, "fonte": None, "n": 0, "erro_live": None}
    live_df = None
    if prefer_live:
        try:
            live_raw = fetch_sisreg_live()
            mun = _municipios_para_mapa()
            if mun.empty:
                mun = pd.read_csv(ROOT / "data" / "municipios_mt.csv") if (ROOT / "data" / "municipios_mt.csv").exists() else pd.DataFrame()
            if mun.empty and "territorio_norm" in live_raw.columns:
                # sem mapa IBGE — grava só com território (painel exige cod_ibge)
                raise RuntimeError("Live OK, mas sem resumo_municipal_atual para mapear IBGE.")
            live_df = map_live_to_ibge(live_raw, mun)
            if live_df.empty:
                raise RuntimeError("Live OK, mas nenhum território mapeado a IBGE.")
            n = persist_ops_sisreg(live_df)
            meta.update({"ok": True, "fonte": "live", "n": n})
            return meta
        except Exception as exc:  # noqa: BLE001
            meta["erro_live"] = str(exc)

    csv_df = load_sisreg_csv(csv_path)
    n = persist_ops_sisreg(csv_df)
    meta.update({"ok": True, "fonte": csv_df["fonte"].iloc[0] if len(csv_df) else "csv", "n": n})
    return meta
