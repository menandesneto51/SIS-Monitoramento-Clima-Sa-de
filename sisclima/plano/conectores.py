# -*- coding: utf-8 -*-
"""Coleta dos indicadores automáticos a partir de fontes já usadas pelo ARARAS.

Sem dado, devolve aguardando_fonte — nunca inventa numerador.
"""
from __future__ import annotations

import json
from typing import Any, Callable

import pandas as pd

from sisclima.core.config import ROOT
from sisclima.core.db import read_table, table_exists
from sisclima.core.logging_utils import get_logger
from sisclima.plano.catalogo import carregar_catalogo

log = get_logger(__name__)

N_MT = 142
N_ERS = 16
_cache: dict[str, pd.DataFrame] = {}

USUARIO_SISTEMA = {
    "email": "conector.araras@ses.mt.gov.br",
    "nome": "Conector ARARAS",
    "nivel": "admin",
    "status": "ativo",
    "perfil_plano": "admin_araras",
    "area_id": "",
}

BLOCO_AGUARDANDO = {
    "IND-008": "VIGIÁGUA / SISAGUA",
    "IND-069": "VIGIÁGUA / SISAGUA",
    "IND-070": "VIGIÁGUA / SISAGUA",
    "IND-075": "COVSAM entomologia",
    "IND-076": "COVSAM entomologia",
    "IND-077": "COVSAM entomologia",
    "IND-052": "COVSAN denúncias",
    "IND-053": "COVSAN denúncias",
}
ESTOQUE_DEFASADO = frozenset({"IND-024", "IND-025", "IND-058", "IND-059"})

Leitura = dict[str, Any]


def limpar_cache_coleta() -> None:
    _cache.clear()


def _tabela(*nomes: str) -> pd.DataFrame:
    for nome in nomes:
        if nome in _cache:
            df = _cache[nome]
            if df is not None and not df.empty:
                return df
        try:
            if table_exists(nome):
                df = read_table(nome)
            else:
                df = pd.DataFrame()
        except Exception as exc:  # noqa: BLE001
            log.warning("tabela %s indisponível: %s", nome, exc)
            df = pd.DataFrame()
        _cache[nome] = df if df is not None else pd.DataFrame()
        if not _cache[nome].empty:
            return _cache[nome]
    return pd.DataFrame()


def _tabela_com_fonte(*nomes: str) -> tuple[pd.DataFrame, str]:
    """Primeira tabela local não vazia, com o nome usado na fonte."""
    for nome in nomes:
        df = _tabela(nome)
        if not df.empty:
            return df, nome
    return pd.DataFrame(), nomes[0] if nomes else ""


def _resumo() -> pd.DataFrame:
    return _tabela("resumo_municipal_atual")


def _n_nivel(df: pd.DataFrame, *niveis: str) -> int:
    if df.empty or "nivel" not in df.columns:
        return 0
    s = df["nivel"].astype(str).str.lower().str.strip()
    return int(s.isin(niveis).sum())


def _col(df: pd.DataFrame, *nomes: str) -> str | None:
    lower = {str(c).lower(): c for c in df.columns}
    for n in nomes:
        if n.lower() in lower:
            return lower[n.lower()]
    return None


_IBGE_IGNORADO = {"510000", "5100000", ""}
_ZSCORE_PRESSAO_VERMELHO = 2.0  # índice de pressão: vermelha se z-score >= 2
_PLACEHOLDER_REG = {
    "",
    "nan",
    "none",
    "nat",
    "regional não informada",
    "regional nao informada",
}
_SINAN_AGRAVO = {
    "IND-062": ("triatom|barbeiro|chagas", "triatomíneos/Chagas"),
    "IND-063": ("peconh|serpente|escorp|aranha", "peçonhentos"),
    "IND-064": ("leishman", "leishmaniose"),
    "IND-066": ("anopheles|criadouro|malar", "Anopheles/malária (proxy até LIRAa)"),
    "IND-067": ("malar", "malaria"),
}


def _serie_ibge(df: pd.DataFrame, col: str) -> pd.Series:
    return (
        df[col]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.extract(r"(\d+)", expand=False)
        .fillna("")
        .str.strip()
    )


def _n_mun_mt(df: pd.DataFrame, mun_col: str | None = None) -> int:
    """Municípios de MT com IBGE válido. Exclui 510000 (município ignorado)."""
    if df is None or df.empty:
        return 0
    col = mun_col or _col(df, "cod_ibge", "ibge")
    if not col:
        return 0
    s = _serie_ibge(df, col)
    s = s[s.str.startswith("51") & ~s.isin(_IBGE_IGNORADO)]
    return int(s.nunique())


def _ultimo_por_municipio(df: pd.DataFrame) -> pd.DataFrame:
    mun = _col(df, "cod_ibge", "ibge")
    if df.empty or not mun:
        return df
    if "data" not in df.columns:
        return df
    out = df.copy()
    out["_d"] = pd.to_datetime(out["data"], errors="coerce")
    out = out.sort_values("_d")
    return out.groupby(mun, as_index=False).tail(1)


def leitura_ok(indicador_id: str, num: int, den: int, fonte: str) -> Leitura:
    return {
        "indicador_id": indicador_id,
        "numerador": int(num),
        "denominador": int(den),
        "fonte": fonte,
        "status": "ok",
    }


def leitura_espera(indicador_id: str, motivo: str) -> Leitura:
    return {
        "indicador_id": indicador_id,
        "numerador": None,
        "denominador": None,
        "fonte": None,
        "status": "aguardando_fonte",
        "motivo": motivo,
    }


def _idade_resumo_dias() -> tuple[float | None, str]:
    df = _resumo()
    if df.empty:
        return None, ""
    col = _col(df, "data_referencia", "data")
    if not col:
        return None, ""
    datas = pd.to_datetime(df[col], errors="coerce")
    latest = datas.max()
    if pd.isna(latest):
        return None, ""
    horas = (pd.Timestamp.now() - pd.Timestamp(latest)).total_seconds() / 3600.0
    return horas, str(pd.Timestamp(latest).date())


def coletor_resumo_risco(indicador_id: str) -> Leitura:
    df = _resumo()
    if df.empty:
        return leitura_espera(indicador_id, "resumo_municipal_atual vazio")
    n = len(df)
    if indicador_id in {"IND-006", "IND-068", "IND-060"}:
        col = _col(df, "nivel")
        validos = int(df[col].notna().sum()) if col else 0
        return leitura_ok(indicador_id, validos, max(n, N_MT), "resumo_municipal_atual.nivel")
    if indicador_id == "IND-007":
        return leitura_ok(indicador_id, _n_nivel(df, "vermelha", "roxa"), n, "resumo_municipal_atual.nivel")
    if indicador_id == "IND-013":
        col_pm = _col(df, "pm25", "pm25_ugm3", "pm2_5")
        if not col_pm:
            return leitura_espera(indicador_id, "coluna PM2,5 ausente no resumo")
        s = pd.to_numeric(df[col_pm], errors="coerce")
        mask = s >= 25
        pop_col = _col(df, "populacao", "pop", "populacao_ibge")
        if pop_col:
            pop = pd.to_numeric(df[pop_col], errors="coerce").fillna(0)
            return leitura_ok(
                indicador_id,
                int(pop[mask].sum()),
                max(int(pop.sum()), 1),
                f"resumo.{col_pm}+{pop_col}",
            )
        return leitura_ok(indicador_id, int(mask.sum()), n, f"resumo_municipal_atual.{col_pm}")
    if indicador_id in {"IND-019", "IND-021"}:
        col = _col(df, "ocupacao_leitos_pct", "ocupacao_uti_pct", "ocupacao_pct")
        if not col:
            return leitura_espera(indicador_id, "ocupação de leitos ausente no resumo")
        s = pd.to_numeric(df[col], errors="coerce")
        if indicador_id == "IND-019":
            return leitura_ok(indicador_id, int(s.notna().sum()), n, f"resumo_municipal_atual.{col}")
        return leitura_ok(indicador_id, int((s >= 85).sum()), max(int(s.notna().sum()), 1), f"resumo_municipal_atual.{col}")
    if indicador_id == "IND-032":
        col = _col(df, "pop_vulneravel", "n_territorio_tradicional", "vulneravel")
        if not col:
            geo = _tabela("geo_vulnerabilidade_municipal")
            if geo.empty:
                return leitura_espera(indicador_id, "camada de vulnerabilidade ausente")
            gcol = _col(geo, "cod_ibge", "ibge")
            n_geo = int(geo[gcol].nunique()) if gcol else len(geo)
            return leitura_ok(indicador_id, n_geo, max(n, N_MT), "geo_vulnerabilidade_municipal")
        s = pd.to_numeric(df[col], errors="coerce")
        return leitura_ok(indicador_id, int((s.fillna(0) > 0).sum()), n, f"resumo_municipal_atual.{col}")
    return leitura_espera(indicador_id, "sem regra de resumo para este ID")


def coletor_metadados(indicador_id: str) -> Leitura:
    horas, data_ref = _idade_resumo_dias()
    if horas is None:
        return leitura_espera(indicador_id, "resumo sem data_referencia")
    if indicador_id == "IND-004":
        no_prazo = 1 if horas <= 8 * 24 else 0
        return leitura_ok(indicador_id, no_prazo, 1, f"resumo.data_referencia={data_ref}")
    if indicador_id == "IND-005":
        pub = _timestamp_ultima_rotina()
        if pub is None:
            return leitura_espera(indicador_id, "sem log de rotina para medir latência")
        fecha = pd.Timestamp(data_ref)
        lat_h = (pub - fecha).total_seconds() / 3600.0
        if lat_h < 0:
            lat_h = 0.0
        return leitura_ok(indicador_id, 1 if lat_h <= 24 else 0, 1, f"latencia_h={lat_h:.1f}")
    return leitura_espera(indicador_id, "sem regra de metadado")


def _timestamp_ultima_rotina() -> pd.Timestamp | None:
    logs = ROOT / "logs"
    if not logs.is_dir():
        return None
    arquivos = sorted(logs.glob("rotina_diaria_*.json"))
    if not arquivos:
        return None
    try:
        data = json.loads(arquivos[-1].read_text(encoding="utf-8"))
        ts = data.get("finished_at") or data.get("started_at")
        out = pd.to_datetime(ts, errors="coerce")
        if pd.isna(out):
            return None
        return pd.Timestamp(out)
    except Exception:  # noqa: BLE001
        return None


def _flag_acima_esperado(df: pd.DataFrame) -> tuple[int | None, str]:
    """Usa flags/z-score que o pipeline já grava — não inventa limiar novo."""
    if df is None or df.empty:
        return None, ""
    last = _ultimo_por_municipio(df)
    mun = _col(last, "cod_ibge", "ibge")
    flag = _col(last, "alerta_aumento", "alerta_arbovirus", "acima_esperado", "acima_baseline")
    if flag:
        s = pd.to_numeric(last[flag], errors="coerce").fillna(0)
        return _n_mun_mt(last.loc[s > 0], mun), flag
    zc = _col(last, "zscore_arbovirus", "zscore_notificacoes", "zscore_srag")
    if zc:
        s = pd.to_numeric(last[zc], errors="coerce").fillna(0)
        return _n_mun_mt(last.loc[s >= _ZSCORE_PRESSAO_VERMELHO], mun), f"{zc}>={_ZSCORE_PRESSAO_VERMELHO:g}"
    return None, ""


def coletor_sinan(indicador_id: str) -> Leitura:
    df, fonte = _tabela_com_fonte("epi_sinan_agravos", "epi_arboviroses")
    if df.empty:
        return leitura_espera(indicador_id, "SINAN sem linhas (epi_sinan_agravos)")
    mun_col = _col(df, "cod_ibge", "ibge", "municipio")
    n_mun = _n_mun_mt(df, mun_col)
    if indicador_id == "IND-015":
        return leitura_ok(indicador_id, 1 if n_mun or len(df) else 0, 1, fonte)
    if indicador_id == "IND-016":
        for nome in ("epi_arboviroses", "epi_arboviroses_municipal", "epi_sinan_agravos"):
            cand = _tabela(nome)
            n, col = _flag_acima_esperado(cand)
            if col:
                return leitura_ok(indicador_id, min(n or 0, N_MT), N_MT, f"{nome}.{col}")
        resumo = _resumo()
        n, col = _flag_acima_esperado(resumo)
        if col:
            return leitura_ok(indicador_id, min(n or 0, N_MT), N_MT, f"resumo_municipal_atual.{col}")
        return leitura_espera(indicador_id, "sem z-score/alerta de desvio no pipeline")
    agravo = _col(df, "agravo", "doenca", "cid", "tipo")
    if indicador_id == "IND-073":
        return leitura_ok(indicador_id, min(n_mun, N_MT), N_MT, fonte)
    padrao, rotulo = _SINAN_AGRAVO.get(indicador_id, ("", ""))
    if padrao and agravo:
        s = df[agravo].astype(str).str.lower()
        hit = s.str.contains(padrao, regex=True)
        n = _n_mun_mt(df.loc[hit], mun_col)
        return leitura_ok(indicador_id, min(n, N_MT), N_MT, f"{fonte} {rotulo}")
    return leitura_espera(indicador_id, "agravo não identificado nesta carga SINAN")


def coletor_cnes(indicador_id: str) -> Leitura:
    df, fonte = _tabela_com_fonte(
        "cnes_unidades_geo", "hospital_capacidade_unidade", "ops_cnes_municipio"
    )
    if df.empty:
        return leitura_espera(
            indicador_id,
            "CNES sem estabelecimentos (cnes_unidades_geo/hospital_capacidade_unidade)",
        )
    tipo = _col(df, "grupo_tipo", "tipo", "tipo_unidade")
    lat = _col(df, "lat", "latitude")
    leito = _col(df, "leitos", "leitos_existentes", "qtd_leitos", "leitos_total")
    if indicador_id == "IND-083":
        hosp = df
        if tipo:
            hosp = df[df[tipo].astype(str).str.lower().str.contains("hospital|urgencia|urgência", regex=True, na=False)]
            if hosp.empty:
                hosp = df
        n = max(len(hosp), 1)
        if lat:
            com = int(hosp[lat].notna().sum())
            return leitura_ok(indicador_id, com, n, fonte)
        if leito:
            s = pd.to_numeric(hosp[leito], errors="coerce")
            return leitura_ok(indicador_id, int(s.notna().sum()), n, f"{fonte}.{leito}")
        return leitura_ok(indicador_id, len(hosp), n, fonte)
    return coletor_resumo_risco(indicador_id)


def coletor_estoque(indicador_id: str) -> Leitura:
    df, fonte = _tabela_com_fonte("ops_estoque_autonomia")
    if df.empty:
        return leitura_espera(indicador_id, "tabela de estoque vazia (ops_estoque_autonomia)")
    est = _col(df, "estoque_total", "quantidade", "saldo")
    cons = _col(df, "consumo_medio_diario", "consumo_diario")
    auto = _col(df, "autonomia_dias", "autonomia")
    ok_min = 0
    rupturas = 0
    n = 0
    for _, row in df.iterrows():
        dias = None
        if auto:
            try:
                dias = float(row.get(auto))
            except (TypeError, ValueError):
                dias = None
            if dias is not None and (pd.isna(dias) or dias == float("inf")):
                if dias == float("inf"):
                    dias = 999.0
                else:
                    dias = None
        if dias is None and est:
            try:
                e = float(row.get(est))
                c = float(row.get(cons)) if cons else 0.0
            except (TypeError, ValueError):
                continue
            if c <= 0:
                continue
            dias = e / c
        if dias is None:
            continue
        n += 1
        if dias >= 10:
            ok_min += 1
        if dias < 3:
            rupturas += 1
    if n <= 0:
        return leitura_espera(indicador_id, "sem consumo para calcular autonomia")
    if indicador_id in {"IND-024", "IND-058"}:
        return leitura_ok(indicador_id, ok_min, n, fonte)
    return leitura_ok(indicador_id, rupturas, n, fonte)


def coletor_qualidade(indicador_id: str) -> Leitura:
    aq = _tabela("qualidade_ar_municipal")
    df = aq if not aq.empty else _resumo()
    if df.empty:
        return leitura_espera(indicador_id, "qualidade do ar e resumo vazios")
    mun = _col(df, "cod_ibge", "ibge", "municipio")
    n_mun = int(df[mun].nunique()) if mun else len(df)
    if indicador_id in {"IND-011", "IND-061"}:
        return leitura_ok(indicador_id, 1 if n_mun else 0, 1, "qualidade_ar_municipal" if not aq.empty else "resumo")
    if indicador_id == "IND-012":
        return leitura_ok(indicador_id, n_mun, N_MT, "qualidade_ar_municipal" if not aq.empty else "resumo.pm")
    return coletor_resumo_risco(indicador_id)


def coletor_comunicacao(indicador_id: str) -> Leitura:
    com = _tabela("ops_comunicacao")
    if not com.empty:
        lat = _col(com, "latencia_horas")
        mun = _col(com, "cod_ibge", "ibge", "municipio", "ers")
        n = len(com)
        if indicador_id in {"IND-018", "IND-074"}:
            n_alc = int(com[mun].nunique()) if mun else n
            return leitura_ok(indicador_id, min(n_alc, N_ERS), N_ERS, "ops_comunicacao")
        if indicador_id == "IND-029" and lat:
            s = pd.to_numeric(com[lat], errors="coerce")
            no_prazo = int((s.notna() & (s <= 24)).sum())
            den = max(int(s.notna().sum()), 1)
            return leitura_ok(indicador_id, no_prazo, den, "ops_comunicacao.latencia_horas")
        if indicador_id in {"IND-030", "IND-072", "IND-079", "IND-086"}:
            n_alc = int(com[mun].nunique()) if mun else n
            return leitura_ok(indicador_id, n_alc, max(n_alc, N_MT) if n_alc else N_MT, "ops_comunicacao")
    alerts = _tabela("inmet_alertas", "cemaden_alertas")
    if alerts.empty:
        return leitura_espera(indicador_id, "ops_comunicacao e alertas INMET/Cemaden vazios")
    mun = _col(alerts, "cod_ibge", "ibge", "municipio")
    n_alc = int(alerts[mun].nunique()) if mun else min(len(alerts), N_MT)
    if indicador_id in {"IND-018", "IND-074"}:
        return leitura_espera(indicador_id, "sem log de envio às 16 ERS")
    if indicador_id == "IND-029":
        return leitura_espera(indicador_id, "alertas sem timestamp de SLA")
    return leitura_ok(indicador_id, n_alc, N_MT, "inmet_alertas/cemaden_alertas")


def _areas_previstas_plano() -> list[str]:
    cat = carregar_catalogo()
    ids = [
        str(a.get("id") or "")
        for a in cat.get("areas") or []
        if str(a.get("id") or "") not in {"", "multi_area"}
    ]
    if ids:
        return ids
    from sisclima.plano.areas import AREAS_CANONICAS

    return [k for k, _ in AREAS_CANONICAS if k != "multi_area"]


def coletor_portaria(indicador_id: str) -> Leitura:
    from sisclima.plano.participantes import participantes_com_email

    pessoas = participantes_com_email()
    previstas = _areas_previstas_plano()
    if not previstas:
        return leitura_espera(indicador_id, "catálogo sem áreas previstas")
    if indicador_id != "IND-001":
        return leitura_espera(indicador_id, "sem regra de Portaria para este ID")
    if not pessoas:
        return leitura_espera(indicador_id, "Portaria 0590 sem participantes com e-mail")
    cobertas = {str(p.get("area_id") or "") for p in pessoas if str(p.get("area_id") or "") in previstas}
    return leitura_ok(indicador_id, len(cobertas), len(previstas), "plano_el_nino_participantes.yaml")


def coletor_infra(indicador_id: str) -> Leitura:
    df, fonte = _tabela_com_fonte("ops_infraestrutura_unidade", "ops_infraestrutura_resumo")
    if df.empty:
        return leitura_espera(indicador_id, "ops_infraestrutura_unidade vazio")
    if indicador_id != "IND-023":
        return leitura_espera(indicador_id, "sem regra de infra para este ID")
    falha = _col(df, "falha_critica")
    if falha:
        s = pd.to_numeric(df[falha], errors="coerce").fillna(0)
        n_falha = int((s > 0).sum())
        n = max(len(df), 1)
        return leitura_ok(indicador_id, n_falha, n, f"{fonte}.falha_critica")
    resumo_col = _col(df, "unidades_falha")
    if resumo_col:
        n_falha = int(pd.to_numeric(df[resumo_col], errors="coerce").fillna(0).sum())
        tot_col = _col(df, "unidades")
        n = int(pd.to_numeric(df[tot_col], errors="coerce").fillna(0).sum()) if tot_col else max(len(df), 1)
        return leitura_ok(indicador_id, n_falha, max(n, 1), f"{fonte}.unidades_falha")
    return leitura_espera(indicador_id, "sem coluna de falha de infraestrutura")


def _soma_col(df: pd.DataFrame, *nomes: str) -> float | None:
    col = _col(df, *nomes)
    if not col:
        return None
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())


def coletor_sisagua(indicador_id: str) -> Leitura:
    df, fonte = _tabela_com_fonte("ops_sisagua", "sisagua_municipal", "vigiagua_municipal")
    if df.empty:
        return leitura_espera(indicador_id, "sem carga SISAGUA/VIGIÁGUA (ops_sisagua)")
    if indicador_id == "IND-008":
        flag = _col(df, "monitoramento_valido", "valido", "amostra_valida")
        if flag:
            ok = df[pd.to_numeric(df[flag], errors="coerce").fillna(0) > 0]
            n = _n_mun_mt(ok)
            den = _n_mun_mt(df) or N_MT
            return leitura_ok(indicador_id, min(n, den), max(den, 1), f"{fonte}.{flag}")
        n = _soma_col(df, "municipios_validos", "n_validos")
        den = _soma_col(df, "municipios_prioritarios", "n_prioritarios")
        if n is not None and den:
            return leitura_ok(indicador_id, int(n), int(den), fonte)
        n_mun = _n_mun_mt(df)
        if n_mun:
            return leitura_ok(indicador_id, n_mun, N_MT, f"{fonte}.cod_ibge")
        return leitura_espera(indicador_id, "ops_sisagua sem coluna de validade municipal")
    if indicador_id == "IND-069":
        num = _soma_col(df, "amostras_realizadas", "realizadas", "n_amostras")
        den = _soma_col(df, "amostras_planejadas", "planejadas", "n_planejado")
        if num is None or not den:
            return leitura_espera(indicador_id, "ops_sisagua sem amostras realizadas/planejadas")
        return leitura_ok(indicador_id, int(num), int(den), fonte)
    if indicador_id == "IND-070":
        num = _soma_col(df, "saa_mapeadas", "formas_mapeadas", "mapeadas")
        den = _soma_col(df, "saa_identificadas", "formas_identificadas", "identificadas")
        if num is None or not den:
            return leitura_espera(indicador_id, "ops_sisagua sem mapeamento SAA/SAC/SAI")
        return leitura_ok(indicador_id, int(num), int(den), fonte)
    return leitura_espera(indicador_id, "sem regra SISAGUA para este ID")


def coletor_entomologia(indicador_id: str) -> Leitura:
    df, fonte = _tabela_com_fonte("ops_entomologia", "liraa_municipal", "ovitrampa_municipal")
    if df.empty:
        return leitura_espera(indicador_id, "sem base entomológica (ops_entomologia / LIRAa)")
    if indicador_id == "IND-075":
        num = _soma_col(df, "ovitrampas_positivas", "positivas")
        den = _soma_col(df, "ovitrampas_examinadas", "examinadas")
        if num is None or not den:
            return leitura_espera(indicador_id, "ops_entomologia sem ovitrampas positivas/examinadas")
        return leitura_ok(indicador_id, int(num), int(den), fonte)
    if indicador_id == "IND-076":
        ido = _col(df, "ido", "densidade_ovos", "ovos_por_armadilha")
        if ido:
            s = pd.to_numeric(df[ido], errors="coerce")
            n = int((s > 50).sum())
            den = max(_n_mun_mt(df), len(df), 1)
            return leitura_ok(indicador_id, min(n, den), den, f"{fonte}.{ido}>50")
        ovos = _soma_col(df, "n_ovos", "ovos")
        pos = _soma_col(df, "ovitrampas_positivas", "positivas")
        if ovos is None or not pos:
            return leitura_espera(indicador_id, "ops_entomologia sem IDO nem ovos/positivas")
        return leitura_ok(indicador_id, int(ovos), int(pos), fonte)
    if indicador_id == "IND-077":
        iip = _col(df, "iip", "iip_pct", "infestacao_predial", "breteau", "ibreteau")
        if not iip:
            return leitura_espera(indicador_id, "ops_entomologia sem IIP/Breteau")
        s = pd.to_numeric(df[iip], errors="coerce")
        n = int((s > 3.9).sum())
        den = max(_n_mun_mt(df), len(df), 1)
        return leitura_ok(indicador_id, min(n, den), den, f"{fonte}.{iip}>3.9")
    return leitura_espera(indicador_id, "sem regra entomológica para este ID")


def coletor_denuncias(indicador_id: str) -> Leitura:
    df, fonte = _tabela_com_fonte("ops_denuncias", "covsan_denuncias")
    if df.empty:
        return leitura_espera(indicador_id, "sem sistema de denúncias (ops_denuncias)")
    if indicador_id == "IND-052":
        rec = _soma_col(df, "denuncias_recebidas", "recebidas", "n_recebidas")
        resp = _soma_col(df, "denuncias_respondidas", "respondidas", "n_respondidas")
        status = _col(df, "status", "situacao")
        if rec and resp is not None:
            return leitura_ok(indicador_id, int(resp), int(rec), fonte)
        if status:
            s = df[status].astype(str).str.casefold()
            n_resp = int(s.str.contains("respond|encerr|conclu", regex=True, na=False).sum())
            n = max(len(df), 1)
            return leitura_ok(indicador_id, n_resp, n, f"{fonte}.{status}")
        return leitura_espera(indicador_id, "ops_denuncias sem recebidas/respondidas")
    if indicador_id == "IND-053":
        sla = _col(df, "dentro_sla", "no_prazo", "sla_ok")
        prio = _col(df, "prioritaria", "prioritario")
        alvo = df
        if prio:
            alvo = df[pd.to_numeric(df[prio], errors="coerce").fillna(0) > 0]
            if alvo.empty:
                alvo = df
        if sla is not None and not alvo.empty:
            n_ok = int((pd.to_numeric(alvo[sla], errors="coerce").fillna(0) > 0).sum())
            return leitura_ok(indicador_id, n_ok, max(len(alvo), 1), f"{fonte}.dentro_sla")
        rec = _col(df, "data_recebimento", "recebido_em", "data")
        resp = _col(df, "data_resposta", "respondido_em")
        if rec and resp and not alvo.empty:
            delta = (
                pd.to_datetime(alvo[resp], errors="coerce") - pd.to_datetime(alvo[rec], errors="coerce")
            ).dt.total_seconds() / 3600.0
            n_ok = int((delta <= 48).sum())
            n = int(delta.notna().sum())
            if not n:
                return leitura_espera(indicador_id, "ops_denuncias sem timestamps válidos")
            return leitura_ok(indicador_id, n_ok, n, f"{fonte}.latencia<=48h (janela operacional até SLA COVSAN)")
        return leitura_espera(indicador_id, "ops_denuncias sem SLA nem timestamps")
    return leitura_espera(indicador_id, "sem regra de denúncia para este ID")


def _n_ers_resumo() -> tuple[int, str]:
    df = _resumo()
    col = _col(df, "regional_saude", "regiao_saude", "regiao")
    if df.empty or not col:
        return 0, ""
    s = df[col].astype(str).str.strip()
    s = s[~s.str.casefold().isin(_PLACEHOLDER_REG)]
    return int(s.nunique()), f"resumo_municipal_atual.{col}"


def _n_unidades_cnes(filtro: str) -> tuple[int, str]:
    df, fonte = _tabela_com_fonte("cnes_unidades_geo", "hospital_capacidade_unidade", "ops_cnes_municipio")
    if df.empty:
        return 0, ""
    tipo = _col(df, "grupo_tipo", "tipo", "tipo_unidade")
    if tipo and filtro:
        subset = df[df[tipo].astype(str).str.lower().str.contains(filtro, regex=True, na=False)]
        if subset.empty:
            return 0, fonte
        df = subset
    return len(df), fonte


def sugerir_leitura(indicador_id: str) -> dict[str, Any] | None:
    """Valor sugerido para semiautomático. A área confirma; o ARARAS não grava sozinho."""
    from sisclima.plano.sugestoes import sugerir_indicador

    return sugerir_indicador(indicador_id)


COLETORES: dict[str, Callable[[str], Leitura]] = {}
for _iid in ("IND-006", "IND-007", "IND-013", "IND-019", "IND-021", "IND-032", "IND-060", "IND-068"):
    COLETORES[_iid] = coletor_resumo_risco
for _iid in ("IND-004", "IND-005"):
    COLETORES[_iid] = coletor_metadados
for _iid in ("IND-015", "IND-016", "IND-062", "IND-063", "IND-064", "IND-066", "IND-067", "IND-073"):
    COLETORES[_iid] = coletor_sinan
for _iid in ("IND-083",):
    COLETORES[_iid] = coletor_cnes
for _iid in ("IND-024", "IND-025", "IND-058", "IND-059"):
    COLETORES[_iid] = coletor_estoque
for _iid in ("IND-011", "IND-012", "IND-061"):
    COLETORES[_iid] = coletor_qualidade
for _iid in ("IND-018", "IND-029", "IND-030", "IND-072", "IND-074", "IND-079", "IND-086"):
    COLETORES[_iid] = coletor_comunicacao
for _iid in ("IND-001",):
    COLETORES[_iid] = coletor_portaria
for _iid in ("IND-023",):
    COLETORES[_iid] = coletor_infra
for _iid in ("IND-008", "IND-069", "IND-070"):
    COLETORES[_iid] = coletor_sisagua
for _iid in ("IND-075", "IND-076", "IND-077"):
    COLETORES[_iid] = coletor_entomologia
for _iid in ("IND-052", "IND-053"):
    COLETORES[_iid] = coletor_denuncias


def coletar_indicador(indicador_id: str) -> Leitura:
    fn = COLETORES.get(indicador_id)
    if not fn:
        return leitura_espera(indicador_id, "conector ainda não implementado (SISAGUA/entomologia/denúncia)")
    try:
        return fn(indicador_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("Coleta %s falhou: %s", indicador_id, exc)
        return leitura_espera(indicador_id, str(exc))


def coletar_automaticos() -> list[Leitura]:
    limpar_cache_coleta()
    cat = carregar_catalogo()
    autos = [i for i in cat.get("indicadores") or [] if str(i.get("modo_atualizacao") or "") == "automatico"]
    return [coletar_indicador(str(i.get("id"))) for i in autos]


def resumo_monitoramento(leituras: list[Leitura] | None = None) -> dict[str, Any]:
    rows = leituras if leituras is not None else coletar_automaticos()
    ok = [r for r in rows if r.get("status") == "ok"]
    espera = [r for r in rows if r.get("status") != "ok"]
    return {
        "n": len(rows),
        "ok": len(ok),
        "aguardando_fonte": len(espera),
        "leituras": rows,
    }
