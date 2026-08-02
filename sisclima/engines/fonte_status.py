# -*- coding: utf-8 -*-
"""Status de confiabilidade das fontes críticas a cada regeneração.

Persiste `fonte_status_regeneracao` para a sala de situação saber se
DW / IndicaSUS / SISREG / ANA / SIVEP responderam nesta rodada.
"""
from __future__ import annotations

import socket
from typing import Any

import pandas as pd

from sisclima.core.config import as_bool, env
from sisclima.core.db import read_table, table_exists
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)


def _tcp(host: str | None, port: int = 1433, timeout: float = 2.5) -> bool:
    if not host:
        return False
    try:
        with socket.create_connection((str(host), int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _count(table: str) -> int:
    try:
        if not table_exists(table):
            return 0
        df = read_table(table)
        return int(len(df)) if df is not None else 0
    except Exception:  # noqa: BLE001
        return 0


def _munis(table: str) -> int:
    try:
        df = read_table(table)
        if df is None or df.empty or "cod_ibge" not in df.columns:
            return 0
        return int(df["cod_ibge"].astype(str).str.extract(r"(\d+)")[0].nunique())
    except Exception:  # noqa: BLE001
        return 0


def build_fonte_status_regeneracao(*, report: dict[str, Any] | None = None) -> pd.DataFrame:
    """Monta linhas de status por fonte crítica da regeneração."""
    now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    report = report or {}

    dw_host = env("DW_SERVER") or env("DW_HOST")
    ind_host = env("INDICASUS_HOST") or env("INDICASUS_SERVER")
    sis_host = env("SISREG_HOST")

    rows: list[dict[str, Any]] = []

    def add(
        fonte_id: str,
        nome: str,
        *,
        flag: bool,
        tcp_ok: bool | None,
        registros: int,
        municipios: int,
        senha_ok: bool | None,
        detalhe: str,
        status: str,
    ) -> None:
        rows.append(
            {
                "fonte_id": fonte_id,
                "fonte_nome": nome,
                "flag_habilitada": bool(flag),
                "tcp_ok": tcp_ok,
                "senha_configurada": senha_ok,
                "registros": int(registros),
                "municipios_com_dado": int(municipios),
                "status": status,
                "detalhe": detalhe,
                "avaliado_em": now,
            }
        )

    # DW
    dw_flag = as_bool(env("USE_SQLSERVER", "false"), False)
    dw_pw = bool((env("DW_PASSWORD") or "").strip()) and not any(
        t in (env("DW_PASSWORD") or "").upper() for t in ("COLE_AQUI", "SENHA_AQUI", "SUA_SENHA")
    )
    dw_tcp = _tcp(dw_host) if dw_flag else None
    dw_regs = _count("epi_arboviroses_municipal") + _count("sim_obitos_calor_municipal_v6") + _count("gal_positividade_municipal_v6")
    if not dw_flag:
        st, det = "desligado", "USE_SQLSERVER=false — pipeline usa CSV/local"
    elif not dw_pw:
        st, det = "sem_senha", "DW_PASSWORD ausente — use .env Ondas/Meningites ou DW_ENV_FILE"
    elif dw_tcp is False:
        st, det = "rede_indisponivel", f"TCP {dw_host}:1433 falhou (VPN SES?)"
    elif dw_regs == 0:
        st, det = "sem_dado", "Rede/senha ok aparente, mas tabelas DW vazias nesta base"
    else:
        st, det = "ok", f"Host {dw_host} · registros derivados={dw_regs}"
    add("dw_ses", "Data Warehouse SES", flag=dw_flag, tcp_ok=dw_tcp, registros=dw_regs, municipios=_munis("epi_arboviroses_municipal"), senha_ok=dw_pw, detalhe=det, status=st)

    # IndicaSUS
    ind_flag = as_bool(env("USE_INDICASUS_OCCUPANCY_SCRIPT", "true"), True)
    ind_pw = bool((env("INDICASUS_PASSWORD") or "").strip())
    ind_tcp = _tcp(ind_host) if ind_flag else None
    ind_regs = _count("hospital_ocupacao_municipio")
    ind_mun = _munis("hospital_ocupacao_municipio")
    occ = read_table("hospital_ocupacao_municipio")
    real = 0
    if occ is not None and not occ.empty and "fonte" in occ.columns:
        fonte = occ["fonte"].astype(str)
        real = int(fonte.str.contains("INDICASUS_TEMPO_REAL", case=False, na=False).sum())
    if not ind_flag:
        st, det = "desligado", "USE_INDICASUS_OCCUPANCY_SCRIPT=false"
    elif ind_tcp is False:
        st, det = "rede_indisponivel", f"TCP {ind_host}:1433 falhou"
    elif ind_regs == 0:
        st, det = "sem_dado", "Sem hospital_ocupacao_municipio"
    elif real == 0:
        st, det = "fallback_cache", f"{ind_mun} munis · ocupação em cache/fallback (não tempo real)"
    else:
        st, det = "ok", f"{real} linhas tempo real · {ind_mun} munis"
    add("indicasus", "IndicaSUS / BdSES", flag=ind_flag, tcp_ok=ind_tcp, registros=ind_regs, municipios=ind_mun, senha_ok=ind_pw, detalhe=det, status=st)

    # SISREG
    sis_flag = True  # step sempre tenta
    sis_pw = bool((env("SISREG_PASSWORD") or "").strip())
    sis_tcp = _tcp(sis_host) if sis_host else None
    sis_regs = _count("ops_sisreg_municipio")
    sis_mun = _munis("ops_sisreg_municipio")
    sis_meta = report.get("sisreg") or {}
    if sis_regs == 0:
        st, det = "sem_dado", str(sis_meta.get("status") or "ops_sisreg_municipio vazio")
    elif sis_tcp is False:
        st, det = "csv_fallback", f"{sis_mun} munis via CSV/cache (TCP SISREG falhou)"
    else:
        st, det = "ok", f"{sis_mun} munis em ops_sisreg_municipio"
    add("sisreg", "SISREG / regulação", flag=sis_flag, tcp_ok=sis_tcp, registros=sis_regs, municipios=sis_mun, senha_ok=sis_pw, detalhe=det, status=st)

    # ANA telemetria / níveis de rio
    ana_flag = as_bool(env("USE_ANA", "true"), True)
    ana_regs = _count("ana_telemetria")
    rio_regs = _count("niveis_rios_municipal")
    ana_mun = _munis("niveis_rios_municipal") or _munis("ana_risco_municipal")
    if not ana_flag:
        st, det = "desligado", "USE_ANA=false"
    elif ana_regs == 0 and rio_regs == 0:
        st, det = "sem_dado", "Sem ana_telemetria — ligue ANA_FETCH_SERIES na VPN ou use sample"
    else:
        st, det = "ok", f"telemetria={ana_regs} · niveis_rios={rio_regs} munis={ana_mun}"
    add("ana_rios", "ANA telemetria / níveis de rios", flag=ana_flag, tcp_ok=None, registros=ana_regs or rio_regs, municipios=ana_mun, senha_ok=None, detalhe=det, status=st)

    # SIVEP
    sivep_regs = _count("epi_sivep_srag")
    if sivep_regs == 0:
        st, det = "sem_dado", "SIVEP vazio — nowcast epi formal indisponível; use perspectiva de pressão"
    else:
        st, det = "ok", f"{sivep_regs} registros epi_sivep_srag"
    add("sivep", "SIVEP-SRAG", flag=as_bool(env("USE_SIVEP_LOCAL", "true"), True), tcp_ok=None, registros=sivep_regs, municipios=_munis("epi_sivep_srag"), senha_ok=None, detalhe=det, status=st)

    # SAN lacuna explícita
    add(
        "san_adaptasus",
        "SAN / insegurança alimentar (AdaptaSUS)",
        flag=False,
        tcp_ok=None,
        registros=_count("san_municipal"),
        municipios=0,
        senha_ok=None,
        detalhe="Lacuna explícita — sem fonte SES municipal pública (SISVAN/CadÚnico sob acordo)",
        status="lacuna",
    )

    # WASH estrutural
    wash_regs = _count("wash_municipal")
    add(
        "wash_censo",
        "WASH (Censo IBGE 2022)",
        flag=as_bool(env("USE_IBGE_WASH", "true"), True),
        tcp_ok=None,
        registros=wash_regs,
        municipios=_munis("wash_municipal"),
        senha_ok=None,
        detalhe="Fonte estrutural (não exige refresh diário)" if wash_regs else "wash_municipal vazio",
        status="estrutural" if wash_regs else "sem_dado",
    )

    return pd.DataFrame(rows)


def ensure_san_lacuna_table() -> pd.DataFrame:
    """Stub explícito: SAN ausente ≠ risco zero."""
    return pd.DataFrame(
        [
            {
                "risco_id": "san",
                "risco_nome": "Insegurança alimentar e nutricional",
                "status_cobertura": "ausente",
                "cobertura_pct": 0.0,
                "fonte": "lacuna_explicita",
                "observacao": "Sem fonte SES municipal pública nesta rodada. Não interpretar como risco zero.",
                "atualizado_em": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        ]
    )
