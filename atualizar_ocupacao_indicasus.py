# -*- coding: utf-8 -*-
"""
Atualizador definitivo da ocupação hospitalar/assistencial do IndicaSUS para o ARARAS MT.

O que faz:
1. Consulta o IndicaSUS/BdSES sem expor credenciais.
2. Calcula ocupação assistencial atual por unidade e município.
3. Resolve geo: UnidadeSaude → Estabelecimento → form.Hospital; sobe PaiLocalidadeId até CodigoIBGE.
4. Grava no backend operacional (Postgres/SQLite):
   - raw_indicasus_ocupacao_tempo_real
   - hospital_ocupacao_unidade
   - hospital_ocupacao_municipio
   - hospital_ocupacao_estado
5. Exporta CSVs em data/output.

Observações metodológicas (alinhado ao filtro SIEGES / dash ocupação):
- SituacaoAtual ≠ Bloqueado → exclui leito com TipoAcompanhamento = 'Bloqueado' do denominador.
- Tipo ∈ {SUS Habilitado, SUS Não Habilitado} → NumeracaoLeitoUnidadeNotificadora.Tipo
  (exclui 'Não SUS').
- TipoLeito ≠ Pronto Atendimento → CategoriaCNES da especialidade do leito
  (Nome NOT LIKE 'Pronto Atendimento%').
- Unidades listadas em UNIDADES_EXCLUIDAS_SIEGES ficam de fora (UPA, unidade mista, etc.).
- Ocupação principal = movimentos 'Acompanhamento' / leitos elegíveis (numeração ativa).
- Higienização e reservado entram no denominador, mas não no numerador.
- A ocupacao_pct é limitada entre 0 e 100 para uso no estágio de risco.
- Não seleciona campos nominais de paciente, CPF, CNS, telefone ou endereço.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from dotenv import load_dotenv

from sisclima.core.db import write_df, backend_name, read_table

try:
    import pyodbc as _pyodbc
except ImportError:  # Docker slim / Linux sem ODBC
    _pyodbc = None

try:
    import pymssql as _pymssql
except ImportError:
    _pymssql = None


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

# Unidades fora do denominador SIEGES (lista institucional do dash).
UNIDADES_EXCLUIDAS_SIEGES = [
    "INSTITUTO DOIS PINHEIROS DE SINOP",
    "MATERNIDADE DR FRANCISCO LUSTOSA DE FIGUEIREDO",
    "METROPOLITANO HOSPITAL ESTADUAL LOUSITE FERREIRA DA SILVA",
    "SANTA CASA",
    "VITALE CLINICA DE OLHOS",
    "VIVENTI HOSPITAL",
    "UNIDADE DE PRONTO ATENDIMENTO",
    "UNIDADE MISTA DE SAUDE DE NOVA OLIMPIA NOVA OLIMPIA",
    "UNIDADE MISTA DE SAUDE IGNACIO KONOPKA",
    "UPA 24 HORAS DR. BOLIVAR AMANCIO DE CARVALHO",
    "UPA FREI OSVALDO",
    "UPA UNIDADE DE PRONTO ATENDIMENTO DRA ANETE MARIA MOTA MARIA",
    "UPA UNIDADE DE PRONTO ATENDIMENTO SARA AKEMI ICHICA",
]


def _sql_excluir_unidades_sieges(alias_nome: str = "NomeUnidadeResolvido") -> str:
    """Cláusula SQL: exclui nomes exatos e padrões UPA / pronto atendimento / unidade mista."""
    values = ", ".join(
        "(N'" + n.replace("'", "''") + "')" for n in UNIDADES_EXCLUIDAS_SIEGES
    )
    # Normaliza espaços duplos (cadastro IndicaSUS: "Pronto  Atendimento").
    norm = f"REPLACE(REPLACE(UPPER(LTRIM(RTRIM(ISNULL({alias_nome}, N'')))), N'  ', N' '), N'  ', N' ')"
    return f"""
      AND {norm} NOT IN (
          SELECT UPPER(LTRIM(RTRIM(v))) FROM (VALUES {values}) AS t(v)
      )
      AND {norm} NOT LIKE N'%PRONTO ATENDIMENTO%'
      AND {norm} NOT LIKE N'%UNIDADE MISTA%'
      AND {norm} NOT LIKE N'UPA %'
      AND {norm} NOT LIKE N'UPA/%'
      AND {norm} NOT LIKE N'%DOIS PINHEIROS%'
      AND {norm} NOT LIKE N'%LUSTOSA%'
      AND {norm} NOT LIKE N'%LOUSITE%'
      AND {norm} NOT LIKE N'%VITALE CLINICA%'
      AND {norm} NOT LIKE N'%VIVENTI HOSPITAL%'
"""


# Numeração ativa + filtros SIEGES (SituacaoAtual / Tipo / TipoLeito / unidades).
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
unidade_nome AS (
    SELECT
        r.UnidadeNotificadoraId,
        r.DataReferencia,
        r.UnidadeNotificadoraLeitoDataReferenciaId,
        -- Leitos IndicaSUS: preferir form.Hospital (mesmo Id pode colidir com UnidadeSaude).
        COALESCE(h.Nome, e.NomeFantasia, us.NomeUnidade) AS NomeUnidadeResolvido,
        COALESCE(h.LocalidadeId, e.LocalidadeId, us.LocalidadeId) AS LocalidadeId,
        us.Latitude,
        us.Longitude,
        CASE
            WHEN h.LocalidadeId IS NOT NULL THEN 'Hospital'
            WHEN e.LocalidadeId IS NOT NULL THEN 'Estabelecimento'
            WHEN us.LocalidadeId IS NOT NULL THEN 'UnidadeSaude'
            ELSE NULL
        END AS fonte_geo_unidade
    FROM ref r
    LEFT JOIN form.Hospital h
        ON h.FormHospitalId = r.UnidadeNotificadoraId
    LEFT JOIN dbo.Estabelecimento e
        ON e.EstabelecimentoId = r.UnidadeNotificadoraId
    LEFT JOIN dbo.UnidadeSaude us
        ON us.UnidadeSaudeId = r.UnidadeNotificadoraId
),
leitos AS (
    SELECT
        u.UnidadeNotificadoraId,
        u.DataReferencia,
        u.NomeUnidadeResolvido,
        u.LocalidadeId,
        u.Latitude,
        u.Longitude,
        u.fonte_geo_unidade,
        n.NumeracaoLeitoUnidadeNotificadoraId,
        n.Tipo AS TipoSUS,
        l.LeitoId,
        l.TipoLeito,
        l.ClassificacaoId
    FROM unidade_nome u
    INNER JOIN ind.UnidadeNotificadoraLeito unl
        ON unl.UnidadeNotificadoraLeitoDataReferenciaId = u.UnidadeNotificadoraLeitoDataReferenciaId
    INNER JOIN ind.NumeracaoLeitoUnidadeNotificadora n
        ON n.UnidadeNotificadoraLeitoId = unl.UnidadeNotificadoraLeitoId
    INNER JOIN ind.Leito l
        ON l.LeitoId = unl.LeitoId
    LEFT JOIN ind.VW_GBSAG_Especialidade esp
        ON esp.EspecialidadeId = n.EspecialidadeId
    LEFT JOIN ind.VW_GBSAG_CategoriaCNES cat
        ON cat.CategoriaCNESId = esp.CategoriaCNESId
    WHERE ISNULL(n.Inativo, 0) = 0
      AND ISNULL(l.Inativo, 0) = 0
      AND ISNULL(l.ProvisorioUPAUBS, 0) = 0
      AND n.Tipo IN (N'SUS Habilitado', N'SUS Não Habilitado')
      AND (cat.Nome IS NULL OR cat.Nome NOT LIKE N'Pronto Atendimento%')
      __EXCLUIR_UNIDADES__
),
mov0 AS (
    SELECT
        al.NumeracaoLeitoUnidadeNotificadoraId,
        al.TipoAcompanhamento,
        al.DataAcompanhamento,
        ROW_NUMBER() OVER (
            PARTITION BY al.NumeracaoLeitoUnidadeNotificadoraId
            ORDER BY
                al.DataAcompanhamento DESC,
                al.DataModificacao DESC,
                al.AcompanhamentoLeitoId DESC
        ) AS rn_mov
    FROM ind.AcompanhamentoLeito al
    WHERE al.DataAcompanhamentoSaida IS NULL
      AND al.NumeracaoLeitoUnidadeNotificadoraId IS NOT NULL
),
mov AS (
    SELECT *
    FROM mov0
    WHERE rn_mov = 1
),
base AS (
    SELECT
        le.*,
        m.TipoAcompanhamento,
        m.DataAcompanhamento AS DataAcompanhamentoMov
    FROM leitos le
    LEFT JOIN mov m
        ON m.NumeracaoLeitoUnidadeNotificadoraId = le.NumeracaoLeitoUnidadeNotificadoraId
),
agg AS (
    SELECT
        UnidadeNotificadoraId,
        NomeUnidadeResolvido AS NomeUnidade,
        LocalidadeId,
        Latitude,
        Longitude,
        fonte_geo_unidade,
        TipoLeito,
        ClassificacaoId,
        MAX(DataReferencia) AS DataReferencia,
        MAX(DataAcompanhamentoMov) AS ultima_movimentacao,
        SUM(CASE WHEN ISNULL(TipoAcompanhamento, N'') <> N'Bloqueado' THEN 1 ELSE 0 END) AS leitos_existentes,
        SUM(
            CASE
                WHEN ISNULL(TipoAcompanhamento, N'') <> N'Bloqueado'
                 AND TipoSUS = N'SUS Habilitado' THEN 1
                ELSE 0
            END
        ) AS leitos_sus,
        SUM(CASE WHEN TipoAcompanhamento = N'Acompanhamento' THEN 1 ELSE 0 END) AS leitos_ocupados,
        SUM(CASE WHEN TipoAcompanhamento = N'Bloqueado' THEN 1 ELSE 0 END) AS leitos_bloqueados_movimento,
        SUM(CASE WHEN TipoAcompanhamento = N'Higienização' THEN 1 ELSE 0 END) AS leitos_higienizacao,
        SUM(CASE WHEN TipoAcompanhamento = N'Reservado' THEN 1 ELSE 0 END) AS leitos_reservados,
        SUM(CASE WHEN TipoAcompanhamento IS NOT NULL THEN 1 ELSE 0 END) AS movimentos_ativos_dedup,
        CAST(0 AS int) AS leitos_bloqueados_cadastro
    FROM base
    GROUP BY
        UnidadeNotificadoraId,
        NomeUnidadeResolvido,
        LocalidadeId,
        Latitude,
        Longitude,
        fonte_geo_unidade,
        TipoLeito,
        ClassificacaoId
)
SELECT
    LocalidadeId,
    UnidadeNotificadoraId,
    NomeUnidade,
    Latitude,
    Longitude,
    TipoLeito,
    ClassificacaoId,
    DataReferencia,
    ultima_movimentacao,
    leitos_existentes,
    leitos_sus,
    leitos_ocupados,
    leitos_bloqueados_cadastro,
    leitos_bloqueados_movimento,
    leitos_higienizacao,
    leitos_reservados,
    movimentos_ativos_dedup,
    CAST(
        100.0 * leitos_ocupados / NULLIF(leitos_existentes, 0)
        AS decimal(10, 2)
    ) AS ocupacao_pct_bruta,
    CASE
        WHEN leitos_ocupados > leitos_existentes AND leitos_existentes > 0 THEN 1
        ELSE 0
    END AS flag_ocupacao_maior_capacidade,
    CASE WHEN LocalidadeId IS NULL THEN 1 ELSE 0 END AS flag_unidade_sem_localidade,
    fonte_geo_unidade
FROM agg
WHERE leitos_existentes > 0
   OR leitos_ocupados > 0
   OR leitos_bloqueados_movimento > 0;
"""

SQL_OCUPACAO_UNIDADE_TIPO = SQL_OCUPACAO_UNIDADE_TIPO.replace(
    "__EXCLUIR_UNIDADES__",
    _sql_excluir_unidades_sieges("u.NomeUnidadeResolvido"),
)


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


def conectar_indicasus() -> Any:
    """Conecta ao BdSES. Preferência: pyodbc (Windows); fallback pymssql (Docker Linux)."""
    load_dotenv(override=True)
    driver = (os.getenv("INDICASUS_DRIVER") or os.getenv("DW_DRIVER") or "ODBC Driver 18 for SQL Server").strip()
    server = (os.getenv("INDICASUS_HOST") or os.getenv("INDICASUS_SERVER") or "").strip()
    database = (os.getenv("INDICASUS_DATABASE") or os.getenv("INDICASUS_DB") or "BdSES").strip()
    encrypt = (os.getenv("INDICASUS_ENCRYPT") or os.getenv("DW_ENCRYPT") or "no").strip()
    trust = (
        os.getenv("INDICASUS_TRUST_SERVER_CERTIFICATE") or os.getenv("DW_TRUST_SERVER_CERTIFICATE") or "yes"
    ).strip()
    port_env = (os.getenv("INDICASUS_PORT") or os.getenv("DW_PORT") or "1433").strip()
    try:
        default_port = int(port_env)
    except ValueError:
        default_port = 1433

    ind_user = (os.getenv("INDICASUS_USER") or "").strip() or None
    ind_password = os.getenv("INDICASUS_PASSWORD")
    if ind_password is not None:
        ind_password = ind_password.strip() or None
    dw_user = (os.getenv("DW_USER") or "").strip() or None
    dw_password = os.getenv("DW_PASSWORD")
    if dw_password is not None:
        dw_password = dw_password.strip() or None
    use_dw_cred = str(os.getenv("INDICASUS_USE_DW_CREDENTIALS", "false")).strip().lower() in {
        "1", "true", "yes", "y", "sim",
    }

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
    if _pyodbc is None and _pymssql is None:
        raise RuntimeError(
            "Nem pyodbc nem pymssql estão instalados. "
            "No Docker use a imagem com pymssql; no Windows instale pyodbc + ODBC 18."
        )

    h_clean, port = _parse_sql_host_port(server, default_port)
    if not _tcp_reachable(h_clean, port, timeout=3.0):
        raise RuntimeError(
            f"IndicaSUS/BdSES inacessível na rede (TCP {h_clean}:{port} falhou). "
            "Conecte-se à VPN/rede corporativa SES-MT e tente novamente."
        )

    server_targets = [h_clean, f"{h_clean},{port}", f"tcp:{h_clean},{port}"]
    errors: list[str] = []

    # Docker Linux: pymssql primeiro (sem ODBC). Windows: pyodbc primeiro.
    prefer_pymssql = _pyodbc is None and _pymssql is not None

    for auth_name, user, password in auth_modes:
        if not user or not password:
            errors.append(f"{auth_name}: usuário/senha ausentes")
            continue

        if prefer_pymssql or _pymssql is not None:
            try:
                conn = _pymssql.connect(
                    server=h_clean,
                    user=user,
                    password=password,
                    database=database,
                    port=port,
                    login_timeout=15,
                    timeout=120,
                )
                print(f"[OK] IndicaSUS/BdSES conectado via pymssql/{auth_name} @ {h_clean}:{port}/{database}")
                return conn
            except Exception as e:
                errors.append(f"pymssql/{auth_name}@{h_clean}:{port}: {e}")

        if _pyodbc is not None:
            for server_target in server_targets:
                try:
                    conn = _pyodbc.connect(
                        f"DRIVER={{{driver}}};"
                        f"SERVER={server_target};"
                        f"DATABASE={database};"
                        f"UID={user};"
                        f"PWD={password};"
                        f"Encrypt={encrypt};"
                        f"TrustServerCertificate={trust};"
                        "Connection Timeout=15;"
                    )
                    print(f"[OK] IndicaSUS/BdSES conectado via pyodbc/{auth_name} @ {server_target}/{database}")
                    return conn
                except Exception as e:
                    errors.append(f"pyodbc/{auth_name}@{server_target}: {e}")

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
    """Universo IBGE-MT (≈142). Preferir resumo/IBGE; CSVs de amostra (12 munis) são ignorados."""

    def _from_frame(df: pd.DataFrame, origem: Path) -> tuple[pd.DataFrame, Path] | None:
        if df is None or df.empty or "cod_ibge" not in df.columns:
            return None
        out = pd.DataFrame(
            {
                "cod_ibge": df["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False),
                "municipio_base": (
                    df["municipio"].astype(str)
                    if "municipio" in df.columns
                    else (df["municipio_base"].astype(str) if "municipio_base" in df.columns else pd.NA)
                ),
            }
        )
        out = out.dropna(subset=["cod_ibge"]).drop_duplicates("cod_ibge")
        out["cod_ibge_6"] = out["cod_ibge"].str.slice(0, 6)
        out = out.dropna(subset=["cod_ibge_6"]).drop_duplicates("cod_ibge_6")
        if len(out) < 100:
            return None
        return out[["cod_ibge_6", "cod_ibge", "municipio_base"]], origem

    try:
        resumo = read_table("resumo_municipal_atual")
        got = _from_frame(resumo, Path("db:resumo_municipal_atual"))
        if got is not None:
            return got
    except Exception:
        pass

    try:
        from sisclima.ingestion.ibge_municipios import load_or_refresh_municipios

        mun = load_or_refresh_municipios()
        got = _from_frame(mun, Path("ibge:municipios_mt"))
        if got is not None:
            return got
    except Exception:
        pass

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
            if len(out) >= 100:
                return out, path
        if "cod_ibge" in cols:
            got = _from_frame(
                pd.DataFrame(
                    {
                        "cod_ibge": df[cols["cod_ibge"]],
                        "municipio": df[cols["municipio"]] if "municipio" in cols else pd.NA,
                    }
                ),
                path,
            )
            if got is not None:
                return got

    raise FileNotFoundError(
        "Não encontrei base territorial MT completa (≥100 municípios com cod_ibge). "
        "Rode a ETL para popular resumo_municipal_atual ou use municipios_mt_base_2025.csv."
    )


def buscar_localidades(con: Any, localidade_ids: Iterable[str]) -> pd.DataFrame:
    """Resolve LocalidadeId → IBGE municipal (sobe PaiLocalidadeId até achar CodigoIBGE)."""
    ids = [str(x) for x in localidade_ids if pd.notna(x) and str(x).strip()]
    if not ids:
        return pd.DataFrame(
            columns=["LocalidadeId", "municipio_indicasus", "cod_ibge_6", "PaiLocalidadeId", "CodigoRFB"]
        )

    valores = ",".join(repr(x) for x in sorted(set(ids)))
    # Bairro/zona costuma ter CodigoIBGE nulo; o município fica 2–4 níveis acima.
    sql = f"""
        SELECT
            l0.LocalidadeId,
            COALESCE(l0.Nome, l1.Nome, l2.Nome, l3.Nome, l4.Nome) AS municipio_indicasus,
            COALESCE(l0.CodigoIBGE, l1.CodigoIBGE, l2.CodigoIBGE, l3.CodigoIBGE, l4.CodigoIBGE) AS cod_ibge_6,
            l0.PaiLocalidadeId,
            COALESCE(l0.CodigoRFB, l1.CodigoRFB, l2.CodigoRFB, l3.CodigoRFB, l4.CodigoRFB) AS CodigoRFB,
            COALESCE(
                CASE WHEN l0.CodigoIBGE IS NOT NULL THEN l0.Nome END,
                CASE WHEN l1.CodigoIBGE IS NOT NULL THEN l1.Nome END,
                CASE WHEN l2.CodigoIBGE IS NOT NULL THEN l2.Nome END,
                CASE WHEN l3.CodigoIBGE IS NOT NULL THEN l3.Nome END,
                CASE WHEN l4.CodigoIBGE IS NOT NULL THEN l4.Nome END
            ) AS municipio_ibge_nome
        FROM dbo.Localidade l0
        LEFT JOIN dbo.Localidade l1 ON l1.LocalidadeId = l0.PaiLocalidadeId
        LEFT JOIN dbo.Localidade l2 ON l2.LocalidadeId = l1.PaiLocalidadeId
        LEFT JOIN dbo.Localidade l3 ON l3.LocalidadeId = l2.PaiLocalidadeId
        LEFT JOIN dbo.Localidade l4 ON l4.LocalidadeId = l3.PaiLocalidadeId
        WHERE l0.LocalidadeId IN ({valores})
    """
    loc = pd.read_sql(sql, con)
    # Preferir nome do nó que carregou o IBGE (município), não o bairro.
    if "municipio_ibge_nome" in loc.columns:
        loc["municipio_indicasus"] = loc["municipio_ibge_nome"].fillna(loc["municipio_indicasus"])
        loc = loc.drop(columns=["municipio_ibge_nome"])
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
    # Uma linha por município IBGE (várias LocalidadeId/bairros da mesma cidade).
    group_cols = ["cod_ibge", "cod_ibge_6"]
    for c in ("municipio_base",):
        if c in df.columns:
            group_cols.append(c)

    nome_ind = (
        df.groupby("cod_ibge", dropna=False)["municipio_indicasus"]
        .agg(lambda s: s.dropna().astype(str).value_counts().index[0] if s.dropna().size else pd.NA)
        .rename("municipio_indicasus")
        if "municipio_indicasus" in df.columns
        else None
    )

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
    if nome_ind is not None:
        agg = agg.merge(nome_ind.reset_index(), on="cod_ibge", how="left")
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
