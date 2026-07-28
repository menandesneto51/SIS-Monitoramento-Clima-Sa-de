# -*- coding: utf-8 -*-
"""
Atualizador definitivo da ocupação hospitalar/assistencial do IndicaSUS para o SIS Clima-Saúde.

O que faz:
1. Consulta o IndicaSUS/BdSES sem expor credenciais.
2. Calcula ocupação assistencial atual por unidade e município.
3. Converte LocalidadeId -> cod_ibge de 7 dígitos usando dbo.Localidade + base territorial MT.
4. Grava no SQLite do projeto:
   - raw_indicasus_ocupacao_tempo_real
   - hospital_ocupacao_unidade
   - hospital_ocupacao_municipio
   - hospital_ocupacao_estado
5. Exporta CSVs em data/output.

Observações metodológicas:
- A ocupação operacional principal usa "Acompanhamento" ativo.
- Bloqueio, higienização e reservado são mantidos como indicadores auxiliares de disponibilidade,
  mas não entram na ocupação_pct assistencial principal.
- A ocupacao_pct é limitada entre 0 e 100 para uso no estágio de risco.
- Não seleciona campos nominais de paciente, CPF, CNS, telefone ou endereço.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

import pandas as pd
import pyodbc
from dotenv import load_dotenv

from sisclima.core.db import write_df, backend_name, read_table


OUTDIR = Path("data/output")
OUT_UNIDADE = OUTDIR / "hospital_ocupacao_unidade.csv"
OUT_MUNICIPIO = OUTDIR / "hospital_ocupacao_municipio.csv"
OUT_ESTADO = OUTDIR / "hospital_ocupacao_estado.csv"
OUT_RAW = OUTDIR / "raw_indicasus_ocupacao_tempo_real.csv"

# Cache/fallback quando BdSES rejeita login (senha expirada/rede).
CANDIDATOS_OCUPACAO_CACHE = [
    OUT_MUNICIPIO,
    Path("data/public/hospital_ocupacao_municipio.csv"),
    Path("../Monitoramento ondas de calor/data/public/hospital_ocupacao_municipio.csv"),
    Path(r"C:\Users\Menandesneto\OneDrive\CIEVS MT\Monitoramento ondas de calor\data\public\hospital_ocupacao_municipio.csv"),
]

CANDIDATOS_BASE_MT = [
    Path("data/input/municipios_mt_base_2025.csv"),
    Path("data/geo/municipios_mt_base_2025.csv"),
    Path("data/output/municipios_mt_base_2025.csv"),
    Path("municipios_mt_base_2025.csv"),
    Path("data/input/populacao_municipal_mt_2020_2025.csv"),
    Path("data/input/populacao_municipios.csv"),
    Path("data/input/municipios_mt.csv"),
    Path("data/input/municipios_metadata.csv"),
    Path("data/sample/populacao_municipios.csv"),
    Path("data/sample/municipios_metadata.csv"),
]


SQL_OCUPACAO_UNIDADE_TIPO = r"""
WITH ref0 AS (
    SELECT
        r.*,
        ROW_NUMBER() OVER (
            PARTITION BY r.UnidadeNotificadoraId
            ORDER BY r.DataReferencia DESC, r.UnidadeNotificadoraLeitoDataReferenciaId DESC
        ) AS rn
    FROM ind.UnidadeNotificadoraLeitoDataReferencia r
),
ref AS (
    SELECT *
    FROM ref0
    WHERE rn = 1
),
cap AS (
    SELECT
        r.UnidadeNotificadoraId,
        r.DataReferencia,
        l.TipoLeito,
        l.ClassificacaoId,
        SUM(ISNULL(unl.QtdExistente, 0)) AS leitos_existentes,
        SUM(ISNULL(unl.QtdSUS, 0)) AS leitos_sus,
        SUM(ISNULL(unl.QtdBloqueada, 0)) AS leitos_bloqueados_cadastro
    FROM ref r
    INNER JOIN ind.UnidadeNotificadoraLeito unl
        ON unl.UnidadeNotificadoraLeitoDataReferenciaId = r.UnidadeNotificadoraLeitoDataReferenciaId
    INNER JOIN ind.Leito l
        ON l.LeitoId = unl.LeitoId
    WHERE ISNULL(l.Inativo, 0) = 0
    GROUP BY
        r.UnidadeNotificadoraId,
        r.DataReferencia,
        l.TipoLeito,
        l.ClassificacaoId
),
mov0 AS (
    SELECT
        al.AcompanhamentoLeitoId,
        al.NumeracaoLeitoUnidadeNotificadoraId,
        COALESCE(iun.UnidadeNotificadoraId, r.UnidadeNotificadoraId) AS UnidadeNotificadoraId,
        COALESCE(al.LeitoId, unl.LeitoId) AS LeitoIdResolvido,
        al.TipoAcompanhamento,
        al.InternacaoSUS,
        al.TipoInternacaoSUS,
        al.DataAcompanhamento,
        al.DataCadastro,
        al.DataModificacao,
        al.MotivoBloqueioId,
        ROW_NUMBER() OVER (
            PARTITION BY
                COALESCE(
                    CAST(al.NumeracaoLeitoUnidadeNotificadoraId AS bigint),
                    -CAST(al.AcompanhamentoLeitoId AS bigint)
                )
            ORDER BY
                al.DataAcompanhamento DESC,
                al.DataModificacao DESC,
                al.AcompanhamentoLeitoId DESC
        ) AS rn_mov
    FROM ind.AcompanhamentoLeito al
    LEFT JOIN ind.InternacaoUnidadeNotificadora iun
        ON iun.InternacaoUnidadeNotificadoraId = al.InternacaoUnidadeNotificadoraId
    LEFT JOIN ind.NumeracaoLeitoUnidadeNotificadora nlu
        ON nlu.NumeracaoLeitoUnidadeNotificadoraId = al.NumeracaoLeitoUnidadeNotificadoraId
    LEFT JOIN ind.UnidadeNotificadoraLeito unl
        ON unl.UnidadeNotificadoraLeitoId = nlu.UnidadeNotificadoraLeitoId
    LEFT JOIN ind.UnidadeNotificadoraLeitoDataReferencia r
        ON r.UnidadeNotificadoraLeitoDataReferenciaId = unl.UnidadeNotificadoraLeitoDataReferenciaId
    WHERE al.DataAcompanhamentoSaida IS NULL
),
mov_dedup AS (
    SELECT *
    FROM mov0
    WHERE rn_mov = 1
),
mov AS (
    SELECT
        md.UnidadeNotificadoraId,
        l.TipoLeito,
        l.ClassificacaoId,
        SUM(CASE WHEN md.TipoAcompanhamento = 'Acompanhamento' THEN 1 ELSE 0 END) AS leitos_ocupados,
        SUM(CASE WHEN md.TipoAcompanhamento = 'Bloqueado' THEN 1 ELSE 0 END) AS leitos_bloqueados_movimento,
        SUM(CASE WHEN md.TipoAcompanhamento = 'Higienização' THEN 1 ELSE 0 END) AS leitos_higienizacao,
        SUM(CASE WHEN md.TipoAcompanhamento = 'Reservado' THEN 1 ELSE 0 END) AS leitos_reservados,
        COUNT(*) AS movimentos_ativos_dedup,
        MAX(md.DataAcompanhamento) AS ultima_movimentacao
    FROM mov_dedup md
    LEFT JOIN ind.Leito l
        ON l.LeitoId = md.LeitoIdResolvido
    GROUP BY
        md.UnidadeNotificadoraId,
        l.TipoLeito,
        l.ClassificacaoId
),
integrado AS (
    SELECT
        COALESCE(c.UnidadeNotificadoraId, m.UnidadeNotificadoraId) AS UnidadeNotificadoraId,
        COALESCE(c.TipoLeito, m.TipoLeito) AS TipoLeito,
        COALESCE(c.ClassificacaoId, m.ClassificacaoId) AS ClassificacaoId,
        c.DataReferencia,
        m.ultima_movimentacao,
        ISNULL(c.leitos_existentes, 0) AS leitos_existentes,
        ISNULL(c.leitos_sus, 0) AS leitos_sus,
        ISNULL(c.leitos_bloqueados_cadastro, 0) AS leitos_bloqueados_cadastro,
        ISNULL(m.leitos_ocupados, 0) AS leitos_ocupados,
        ISNULL(m.leitos_bloqueados_movimento, 0) AS leitos_bloqueados_movimento,
        ISNULL(m.leitos_higienizacao, 0) AS leitos_higienizacao,
        ISNULL(m.leitos_reservados, 0) AS leitos_reservados,
        ISNULL(m.movimentos_ativos_dedup, 0) AS movimentos_ativos_dedup
    FROM cap c
    FULL OUTER JOIN mov m
        ON m.UnidadeNotificadoraId = c.UnidadeNotificadoraId
       AND ISNULL(m.TipoLeito, -1) = ISNULL(c.TipoLeito, -1)
       AND ISNULL(m.ClassificacaoId, -1) = ISNULL(c.ClassificacaoId, -1)
)
SELECT
    us.LocalidadeId,
    i.UnidadeNotificadoraId,
    us.NomeUnidade,
    us.Latitude,
    us.Longitude,
    i.TipoLeito,
    i.ClassificacaoId,
    i.DataReferencia,
    i.ultima_movimentacao,
    i.leitos_existentes,
    i.leitos_sus,
    i.leitos_ocupados,
    i.leitos_bloqueados_cadastro,
    i.leitos_bloqueados_movimento,
    i.leitos_higienizacao,
    i.leitos_reservados,
    i.movimentos_ativos_dedup,
    CAST(
        100.0 * i.leitos_ocupados / NULLIF(i.leitos_existentes, 0)
        AS decimal(10, 2)
    ) AS ocupacao_pct_bruta,
    CASE
        WHEN i.leitos_ocupados > i.leitos_existentes AND i.leitos_existentes > 0 THEN 1
        ELSE 0
    END AS flag_ocupacao_maior_capacidade,
    CASE
        WHEN us.LocalidadeId IS NULL THEN 1
        ELSE 0
    END AS flag_unidade_sem_localidade
FROM integrado i
LEFT JOIN dbo.UnidadeSaude us
    ON us.UnidadeSaudeId = i.UnidadeNotificadoraId;
"""


def _parse_sql_host_port(server: str, default_port: int = 1433) -> tuple[str, int]:
    s = (server or "").strip()
    if s.lower().startswith("tcp:"):
        s = s[4:]
    if "," in s:
        host, port_s = s.split(",", 1)
        try:
            return host.strip(), int(port_s.strip())
        except ValueError:
            return host.strip(), default_port
    if "\\" in s:
        # instância nomeada — mantém string completa e porta padrão TCP
        return s, default_port
    return s, default_port


def _tcp_reachable(host: str, port: int, timeout: float = 3.0) -> bool:
    import socket

    try:
        with socket.create_connection((host.split("\\", 1)[0], port), timeout=timeout):
            return True
    except OSError:
        return False


def conectar_indicasus() -> pyodbc.Connection:
    load_dotenv(override=True)
    driver = os.getenv("INDICASUS_DRIVER") or os.getenv("DW_DRIVER") or "ODBC Driver 18 for SQL Server"
    server = os.getenv("INDICASUS_HOST") or os.getenv("INDICASUS_SERVER")
    database = os.getenv("INDICASUS_DATABASE") or os.getenv("INDICASUS_DB") or "BdSES"
    encrypt = os.getenv("INDICASUS_ENCRYPT") or os.getenv("DW_ENCRYPT") or "no"
    trust = os.getenv("INDICASUS_TRUST_SERVER_CERTIFICATE") or os.getenv("DW_TRUST_SERVER_CERTIFICATE") or "yes"
    port_env = os.getenv("INDICASUS_PORT") or os.getenv("DW_PORT") or "1433"
    try:
        default_port = int(port_env)
    except ValueError:
        default_port = 1433

    ind_user = os.getenv("INDICASUS_USER")
    ind_password = os.getenv("INDICASUS_PASSWORD")
    dw_user = os.getenv("DW_USER")
    dw_password = os.getenv("DW_PASSWORD")
    use_dw_cred = str(os.getenv("INDICASUS_USE_DW_CREDENTIALS", "false")).strip().lower() in {
        "1", "true", "yes", "y", "sim",
    }

    # Ordem: credencial IndicaSUS primeiro (padrão); DW só como fallback.
    auth_modes: list[tuple[str, str | None, str | None]] = []
    if use_dw_cred:
        auth_modes.append(("dw_credentials", dw_user or ind_user, dw_password or ind_password))
        if ind_user and ind_password:
            auth_modes.append(("indicasus_credentials", ind_user, ind_password))
    else:
        auth_modes.append(("indicasus_credentials", ind_user or dw_user, ind_password or dw_password))
        if dw_user and dw_password:
            auth_modes.append(("dw_credentials_fallback", dw_user, dw_password))

    if not server:
        raise RuntimeError("Variáveis ausentes no .env: INDICASUS_HOST/INDICASUS_SERVER")

    # BdSES fica só no host IndicaSUS — NÃO tentar DW_HOST (Datawarehouse != BdSES).
    h_clean, port = _parse_sql_host_port(server, default_port)
    if not _tcp_reachable(h_clean, port, timeout=3.0):
        raise RuntimeError(
            f"IndicaSUS/BdSES inacessível na rede (TCP {h_clean}:{port} falhou). "
            "Conecte-se à VPN/rede corporativa SES-MT e tente novamente."
        )

    # Formatos de SERVER: o mesmo do projeto ondas, depois TCP explícito.
    server_targets = [h_clean, f"{h_clean},{port}", f"tcp:{h_clean},{port}"]

    errors: list[str] = []
    for auth_name, user, password in auth_modes:
        if not user or not password:
            errors.append(f"{auth_name}: usuário/senha ausentes")
            continue
        for server_target in server_targets:
            try:
                conn = pyodbc.connect(
                    f"DRIVER={{{driver}}};"
                    f"SERVER={server_target};"
                    f"DATABASE={database};"
                    f"UID={user};"
                    f"PWD={password};"
                    f"Encrypt={encrypt};"
                    f"TrustServerCertificate={trust};"
                    "Connection Timeout=15;"
                )
                print(f"[OK] IndicaSUS/BdSES conectado via {auth_name} @ {server_target}/{database} (user={user})")
                return conn
            except Exception as e:
                errors.append(f"{auth_name}@{server_target}: {e}")
    raise RuntimeError(
        "Falha de autenticação no IndicaSUS/BdSES (rede OK). "
        "Atualize INDICASUS_USER/INDICASUS_PASSWORD no .env junto à equipe IndicaSUS/SES. "
        "Detalhes: " + " | ".join(errors[:4])
    )

def ler_csv_auto(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    if len(df.columns) == 1 and ";" in df.columns[0]:
        df = pd.read_csv(path, sep=";", dtype=str)
    return df


def localizar_base_mt() -> tuple[pd.DataFrame, Path]:
    for path in CANDIDATOS_BASE_MT:
        if not path.exists():
            continue
        df = ler_csv_auto(path)
        cols = {c.lower(): c for c in df.columns}
        if "cod_ibge_6" in cols and "cod_ibge" in cols:
            out = df[[cols["cod_ibge_6"], cols["cod_ibge"]]].copy()
            out.columns = ["cod_ibge_6", "cod_ibge"]
            out["municipio_base"] = df[cols["municipio"]].astype(str) if "municipio" in cols else pd.NA
            out["cod_ibge_6"] = out["cod_ibge_6"].astype(str).str.extract(r"(\d{6})", expand=False)
            out["cod_ibge"] = out["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
            out = out.dropna(subset=["cod_ibge_6", "cod_ibge"]).drop_duplicates("cod_ibge_6")
            return out, path
        if "cod_ibge" in cols:
            out = pd.DataFrame({
                "cod_ibge": df[cols["cod_ibge"]].astype(str).str.extract(r"(\d{7})", expand=False),
                "municipio_base": df[cols["municipio"]].astype(str) if "municipio" in cols else pd.NA,
            })
            out = out.dropna(subset=["cod_ibge"]).drop_duplicates("cod_ibge")
            out["cod_ibge_6"] = out["cod_ibge"].str.slice(0, 6)
            out = out.dropna(subset=["cod_ibge_6"]).drop_duplicates("cod_ibge_6")
            return out[["cod_ibge_6", "cod_ibge", "municipio_base"]], path
    raise FileNotFoundError(
        "Não encontrei base territorial MT com cod_ibge. "
        "Use municipios_mt.csv, populacao_municipios.csv ou municipios_mt_base_2025.csv."
    )


def buscar_localidades(con: pyodbc.Connection, localidade_ids: Iterable[str]) -> pd.DataFrame:
    ids = [str(x) for x in localidade_ids if pd.notna(x) and str(x).strip()]
    if not ids:
        return pd.DataFrame(columns=["LocalidadeId", "municipio_indicasus", "cod_ibge_6", "PaiLocalidadeId", "CodigoRFB"])

    valores = ",".join(repr(x) for x in sorted(set(ids)))
    sql = f"""
        SELECT
            LocalidadeId,
            Nome AS municipio_indicasus,
            CodigoIBGE AS cod_ibge_6,
            PaiLocalidadeId,
            CodigoRFB
        FROM dbo.Localidade
        WHERE LocalidadeId IN ({valores})
    """
    loc = pd.read_sql(sql, con)
    loc["cod_ibge_6"] = loc["cod_ibge_6"].astype(str).str.extract(r"(\d{6})", expand=False)
    return loc


def capar_percentual(valor: pd.Series) -> pd.Series:
    return pd.to_numeric(valor, errors="coerce").clip(lower=0, upper=100)


def preparar_unidade(df: pd.DataFrame, loc: pd.DataFrame, base_mt: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["LocalidadeId"] = out["LocalidadeId"].replace({"nan": pd.NA, "NaN": pd.NA, "": pd.NA})
    out = out.merge(loc, on="LocalidadeId", how="left")
    out = out.merge(base_mt, on="cod_ibge_6", how="left")

    numeric_cols = [
        "UnidadeNotificadoraId", "Latitude", "Longitude", "TipoLeito", "ClassificacaoId",
        "leitos_existentes", "leitos_sus", "leitos_ocupados",
        "leitos_bloqueados_cadastro", "leitos_bloqueados_movimento",
        "leitos_higienizacao", "leitos_reservados", "movimentos_ativos_dedup",
        "ocupacao_pct_bruta", "flag_ocupacao_maior_capacidade", "flag_unidade_sem_localidade"
    ]
    for col in numeric_cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    out["ocupacao_pct"] = capar_percentual(out["ocupacao_pct_bruta"])
    out["flag_sem_cod_ibge"] = out["cod_ibge"].isna().astype(int)
    out["fonte"] = "INDICASUS_TEMPO_REAL"
    out["data_processamento"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

    return out


def preparar_municipio(unidade: pd.DataFrame) -> pd.DataFrame:
    df = unidade[unidade["cod_ibge"].notna()].copy()
    group_cols = ["cod_ibge", "cod_ibge_6", "municipio_base", "municipio_indicasus", "LocalidadeId"]

    agg = (
        df.groupby(group_cols, dropna=False)
        .agg(
            unidades=("UnidadeNotificadoraId", "nunique"),
            ultima_movimentacao=("ultima_movimentacao", "max"),
            leitos_existentes=("leitos_existentes", "sum"),
            leitos_sus=("leitos_sus", "sum"),
            leitos_ocupados=("leitos_ocupados", "sum"),
            leitos_bloqueados_cadastro=("leitos_bloqueados_cadastro", "sum"),
            leitos_bloqueados_movimento=("leitos_bloqueados_movimento", "sum"),
            leitos_higienizacao=("leitos_higienizacao", "sum"),
            leitos_reservados=("leitos_reservados", "sum"),
            movimentos_ativos_dedup=("movimentos_ativos_dedup", "sum"),
            grupos_ocupacao_maior_capacidade=("flag_ocupacao_maior_capacidade", "sum"),
        )
        .reset_index()
    )
    agg["ocupacao_pct_bruta"] = 100 * agg["leitos_ocupados"] / agg["leitos_existentes"].replace({0: pd.NA})
    agg["ocupacao_pct"] = capar_percentual(agg["ocupacao_pct_bruta"])
    agg["fonte"] = "INDICASUS_TEMPO_REAL"
    agg["data_processamento"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    return agg.sort_values(["ocupacao_pct", "leitos_ocupados"], ascending=[False, False])


def preparar_estado(municipio: pd.DataFrame, unidade: pd.DataFrame) -> pd.DataFrame:
    valid = municipio[municipio["cod_ibge"].notna()].copy()
    total_exist = valid["leitos_existentes"].sum()
    total_ocup = valid["leitos_ocupados"].sum()

    estado = pd.DataFrame(
        [
            {
                "uf": "MT",
                "municipios_com_ocupacao": valid["cod_ibge"].nunique(),
                "unidades_com_localidade": int(valid["unidades"].sum()),
                "unidades_sem_localidade": int(unidade["flag_sem_cod_ibge"].sum()),
                "ultima_movimentacao": valid["ultima_movimentacao"].max(),
                "leitos_existentes": total_exist,
                "leitos_sus": valid["leitos_sus"].sum(),
                "leitos_ocupados": total_ocup,
                "leitos_bloqueados_cadastro": valid["leitos_bloqueados_cadastro"].sum(),
                "leitos_bloqueados_movimento": valid["leitos_bloqueados_movimento"].sum(),
                "leitos_higienizacao": valid["leitos_higienizacao"].sum(),
                "leitos_reservados": valid["leitos_reservados"].sum(),
                "ocupacao_pct_bruta": 100 * total_ocup / total_exist if total_exist else pd.NA,
                "ocupacao_pct": min(max(100 * total_ocup / total_exist, 0), 100) if total_exist else pd.NA,
                "fonte": "INDICASUS_TEMPO_REAL",
                "data_processamento": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        ]
    )
    return estado


def preparar_regional(municipio: pd.DataFrame) -> pd.DataFrame:
    """Agrega ocupação por regional de saúde usando vínculo do resumo municipal."""
    if municipio.empty or "cod_ibge" not in municipio.columns:
        return pd.DataFrame()
    resumo = read_table("resumo_municipal_atual")
    if resumo.empty or "cod_ibge" not in resumo.columns:
        return pd.DataFrame()
    ref = resumo.copy()
    ref["cod_ibge"] = ref["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
    ref["regional_saude"] = ref.get("regional_saude", pd.Series(dtype=str)).fillna("Regional não informada").astype(str)
    base = municipio.copy()
    base["cod_ibge"] = base["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
    base = base.merge(
        ref[[c for c in ["cod_ibge", "regional_saude"] if c in ref.columns]].drop_duplicates("cod_ibge"),
        on="cod_ibge",
        how="left",
    )
    base["regional_saude"] = base["regional_saude"].fillna("Regional não informada")
    agg = (
        base.groupby("regional_saude", dropna=False)
        .agg(
            municipios=("cod_ibge", "nunique"),
            leitos_existentes=("leitos_existentes", "sum"),
            leitos_sus=("leitos_sus", "sum"),
            leitos_ocupados=("leitos_ocupados", "sum"),
            leitos_bloqueados_movimento=("leitos_bloqueados_movimento", "sum"),
            leitos_higienizacao=("leitos_higienizacao", "sum"),
            leitos_reservados=("leitos_reservados", "sum"),
        )
        .reset_index()
    )
    agg["ocupacao_pct"] = 100 * agg["leitos_ocupados"] / agg["leitos_existentes"].replace({0: pd.NA})
    agg["ocupacao_pct"] = agg["ocupacao_pct"].clip(0, 100)
    agg["fonte"] = "INDICASUS_TEMPO_REAL_REGIONAL"
    agg["data_processamento"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    return agg


def gravar_base_operacional(tabelas: dict[str, pd.DataFrame]) -> None:
    for nome, df in tabelas.items():
        write_df(df if df is not None else pd.DataFrame(), nome, if_exists="replace")


def _allow_csv_fallback() -> bool:
    return str(os.getenv("INDICASUS_ALLOW_CSV_FALLBACK", "true")).strip().lower() in {
        "1", "true", "yes", "y", "sim",
    }


def carregar_ocupacao_cache() -> tuple[pd.DataFrame, Path]:
    for path in CANDIDATOS_OCUPACAO_CACHE:
        if not path.exists():
            continue
        df = ler_csv_auto(path)
        if df.empty:
            continue
        cols_l = {c.lower(): c for c in df.columns}
        if "ocupacao_pct" not in cols_l and "ocupacao_leitos_pct" not in cols_l:
            continue
        out = df.copy()
        if "fonte" in out.columns:
            base_fonte = out["fonte"].astype(str).str.replace(r"(\|CACHE_CSV)+$", "", regex=True)
            out["fonte"] = base_fonte + "|CACHE_CSV"
        else:
            out["fonte"] = "INDICASUS_CACHE_CSV"
        return out, path
    raise FileNotFoundError(
        "Nenhum CSV de ocupação encontrado para fallback. "
        "Caminhos tentados: " + ", ".join(str(p) for p in CANDIDATOS_OCUPACAO_CACHE)
    )


def _estado_from_municipio(municipio: pd.DataFrame) -> pd.DataFrame:
    valid = municipio.copy()
    if "cod_ibge" in valid.columns:
        valid = valid[valid["cod_ibge"].notna()]
    total_exist = pd.to_numeric(valid.get("leitos_existentes"), errors="coerce").sum()
    total_ocup = pd.to_numeric(valid.get("leitos_ocupados"), errors="coerce").sum()
    return pd.DataFrame(
        [
            {
                "uf": "MT",
                "municipios_com_ocupacao": valid["cod_ibge"].nunique() if "cod_ibge" in valid.columns else len(valid),
                "leitos_existentes": total_exist,
                "leitos_ocupados": total_ocup,
                "ocupacao_pct": min(max(100 * total_ocup / total_exist, 0), 100) if total_exist else pd.NA,
                "fonte": "INDICASUS_CACHE_CSV",
                "data_processamento": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        ]
    )


def _imprimir_resumo(municipio: pd.DataFrame, estado: pd.DataFrame, origem: str) -> None:
    print(f"OK: ocupação IndicaSUS atualizada na base operacional ({origem}).")
    print(f"Backend: {backend_name()}")
    print()
    print("Tabelas gravadas:")
    print("- hospital_ocupacao_municipio")
    print("- hospital_ocupacao_estado")
    print()
    print("Resumo estadual:")
    print(estado.to_string(index=False))
    print()
    print("Top 30 municípios por ocupação:")
    cols = [
        "cod_ibge", "municipio_base", "unidades", "ultima_movimentacao",
        "leitos_existentes", "leitos_sus", "leitos_ocupados", "ocupacao_pct",
        "leitos_bloqueados_movimento", "leitos_higienizacao", "leitos_reservados",
    ]
    cols = [c for c in cols if c in municipio.columns]
    sort_col = "ocupacao_pct" if "ocupacao_pct" in municipio.columns else cols[0]
    print(municipio[cols].sort_values(sort_col, ascending=False).head(30).to_string(index=False))


def main() -> None:
    load_dotenv(override=True)
    OUTDIR.mkdir(parents=True, exist_ok=True)

    try:
        con_ind = conectar_indicasus()
        base_mt, caminho_base = localizar_base_mt()

        raw = pd.read_sql(SQL_OCUPACAO_UNIDADE_TIPO, con_ind)
        loc = buscar_localidades(con_ind, raw["LocalidadeId"].dropna().astype(str).unique())

        unidade = preparar_unidade(raw, loc, base_mt)
        municipio = preparar_municipio(unidade)
        estado = preparar_estado(municipio, unidade)
        regional = preparar_regional(municipio)

        raw.to_csv(OUT_RAW, index=False, encoding="utf-8-sig")
        unidade.to_csv(OUT_UNIDADE, index=False, encoding="utf-8-sig")
        municipio.to_csv(OUT_MUNICIPIO, index=False, encoding="utf-8-sig")
        estado.to_csv(OUT_ESTADO, index=False, encoding="utf-8-sig")

        gravar_base_operacional(
            {
                "raw_indicasus_ocupacao_tempo_real": raw,
                "hospital_ocupacao_unidade": unidade,
                "hospital_ocupacao_municipio": municipio,
                "hospital_ocupacao_estado": estado,
                "hospital_ocupacao_regional": regional,
            }
        )
        print(f"Base territorial usada: {caminho_base}")
        _imprimir_resumo(municipio, estado, "tempo real BdSES")
        return
    except Exception as live_err:
        print(f"[AVISO] Atualização ao vivo IndicaSUS falhou: {live_err}")
        if not _allow_csv_fallback():
            raise

    municipio, caminho_cache = carregar_ocupacao_cache()
    estado = _estado_from_municipio(municipio)
    municipio.to_csv(OUT_MUNICIPIO, index=False, encoding="utf-8-sig")
    estado.to_csv(OUT_ESTADO, index=False, encoding="utf-8-sig")
    gravar_base_operacional(
        {
            "hospital_ocupacao_municipio": municipio,
            "hospital_ocupacao_estado": estado,
            "hospital_ocupacao_regional": pd.DataFrame(),
        }
    )
    print(f"[AVISO] Usando cache CSV: {caminho_cache}")
    _imprimir_resumo(municipio, estado, f"cache CSV ({caminho_cache})")


if __name__ == "__main__":
    main()
