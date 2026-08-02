# -*- coding: utf-8 -*-
"""Ingestão VigiBarragens — vigilância em saúde de populações expostas a barragens.

Contexto (Ministério da Saúde / CGVAM / VIGIPEQ):
- VigiBarragens acompanha municípios e populações expostas a barragens de
  mineração/rejeito, especialmente na Zona de Autossalvamento (ZAS) a jusante.
- O cadastro oficial das barragens é o SIGBM (Sistema Integrado de Gestão de
  Segurança de Barragens de Mineração), da ANM (Agência Nacional de Mineração),
  com Categoria de Risco (CRI), Dano Potencial Associado (DPA) e Nível de
  Emergência (NE1/NE2/NE3).

Fontes:
- Opcional online (JSON): VIGIBARRAGENS_URL (portal aberto SIGBM/ANM).
- Fallback CSV: data/input/vigibarragens_barragens.csv (amostra em data/sample/).

Saídas (tabelas):
- vigibarragens_barragens — inventário por barragem.
- vigibarragens_exposicao_municipal — agregado municipal (exposição/nível SIS).
"""
from __future__ import annotations

import pandas as pd

from sisclima.core.config import APP_CONFIG, ROOT, as_bool, env
from sisclima.core.http_client import http_get
from sisclima.core.logging_utils import get_logger
from sisclima.utils.io import normalize_cols, read_table_safe

log = get_logger(__name__)

# Nível de emergência SIGBM/ANM → nível operacional SIS.
_EMERGENCIA_MAP = {
    "3": "roxa",
    "ne3": "roxa",
    "nivel 3": "roxa",
    "nível 3": "roxa",
    "emergencia nivel 3": "roxa",
    "2": "vermelha",
    "ne2": "vermelha",
    "nivel 2": "vermelha",
    "nível 2": "vermelha",
    "emergencia nivel 2": "vermelha",
    "1": "laranja",
    "ne1": "laranja",
    "nivel 1": "laranja",
    "nível 1": "laranja",
    "emergencia nivel 1": "laranja",
}

_ORDER = {"roxa": 4, "vermelha": 3, "laranja": 2, "amarela": 1, "verde": 0, "cinza": -1}

_BARRAGENS_COLS = [
    "cod_barragem",
    "nome_barragem",
    "empreendedor",
    "cod_ibge",
    "municipio",
    "uf",
    "lat",
    "lon",
    "minerio",
    "categoria_risco",
    "dano_potencial",
    "nivel_emergencia",
    "nivel_emergencia_sis",
    "populacao_zas",
    "situacao_pnsb",
    "data_atualizacao",
    "fonte",
]


def _norm_nivel_emergencia(value) -> str:
    """Normaliza o nível de emergência bruto para o nível operacional SIS."""
    txt = str(value or "").strip().lower()
    if not txt or txt in {"sem emergencia", "sem emergência", "0", "nao", "não", "normal"}:
        return "verde"
    for key, nivel in _EMERGENCIA_MAP.items():
        if key in txt:
            return nivel
    return "verde"


def fetch_vigibarragens_barragens(uf: str | None = None) -> pd.DataFrame:
    """Busca cadastro de barragens (SIGBM/ANM) quando VIGIBARRAGENS_URL estiver configurada.

    Sem URL pública configurada (padrão), retorna vazio e o pipeline usa o CSV.
    """
    if not as_bool(env("USE_VIGIBARRAGENS", "true"), True):
        return pd.DataFrame()

    url = (env("VIGIBARRAGENS_URL") or "").strip()
    if not url:
        return pd.DataFrame()

    uf = (uf if uf is not None else (env("VIGIBARRAGENS_UF") or APP_CONFIG.uf or "MT"))
    uf = str(uf).strip().upper() if uf is not None else ""

    try:
        r = http_get(
            url,
            timeout=int(env("VIGIBARRAGENS_TIMEOUT_SECONDS", "45") or 45),
            ssl_env_key="VIGIBARRAGENS_SSL_VERIFY",
        )
        r.raise_for_status()
        js = r.json()
    except Exception as exc:
        log.warning("Falha ao consultar VigiBarragens/SIGBM (%s): %s", url, exc)
        return pd.DataFrame()

    rows = js.get("barragens") if isinstance(js, dict) else js
    if not isinstance(rows, list) or not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["fonte"] = "SIGBM_ANM"
    if uf and uf not in {"*", "BR", "ALL", "TODAS"} and "uf" in df.columns:
        df = df[df["uf"].astype(str).str.upper().eq(uf)].copy()
    return df.reset_index(drop=True)


def normalize_barragens(df: pd.DataFrame) -> pd.DataFrame:
    """Padroniza o cadastro de barragens para o schema canônico do SIS."""
    if df is None or df.empty:
        return pd.DataFrame(columns=_BARRAGENS_COLS)

    out = df.copy()
    out.columns = [str(c).lower().strip().replace(" ", "_") for c in out.columns]

    rename = {
        "codigo_barragem": "cod_barragem",
        "codigo": "cod_barragem",
        "id_barragem": "cod_barragem",
        "nome": "nome_barragem",
        "barragem": "nome_barragem",
        "empreendimento": "empreendedor",
        "empresa": "empreendedor",
        "codigo_ibge": "cod_ibge",
        "codibge": "cod_ibge",
        "cod_municipio": "cod_ibge",
        "nome_municipio": "municipio",
        "substancia": "minerio",
        "minério": "minerio",
        "categoria_de_risco": "categoria_risco",
        "cri": "categoria_risco",
        "dano_potencial_associado": "dano_potencial",
        "dpa": "dano_potencial",
        "nivel_de_emergencia": "nivel_emergencia",
        "nível_de_emergência": "nivel_emergencia",
        "ne": "nivel_emergencia",
        "populacao_jusante": "populacao_zas",
        "populacao_zas_hab": "populacao_zas",
        "pop_zas": "populacao_zas",
        "latitude": "lat",
        "longitude": "lon",
        "atualizacao": "data_atualizacao",
        "ult_atualizacao": "data_atualizacao",
    }
    out = out.rename(columns={k: v for k, v in rename.items() if k in out.columns})

    if "cod_ibge" in out.columns:
        out["cod_ibge"] = out["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)

    for c in ["lat", "lon", "populacao_zas"]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")

    if "data_atualizacao" in out.columns:
        out["data_atualizacao"] = pd.to_datetime(out["data_atualizacao"], errors="coerce")

    ne_raw = out["nivel_emergencia"] if "nivel_emergencia" in out.columns else pd.Series([""] * len(out))
    out["nivel_emergencia"] = ne_raw.astype(str).str.strip()
    out["nivel_emergencia_sis"] = ne_raw.map(_norm_nivel_emergencia)

    if "fonte" not in out.columns:
        out["fonte"] = "SIGBM"

    for col in _BARRAGENS_COLS:
        if col not in out.columns:
            out[col] = pd.NA

    return out[_BARRAGENS_COLS].reset_index(drop=True)


def load_vigibarragens_csv_fallback() -> pd.DataFrame:
    """Lê CSV local (data/input) e, se ausente, a amostra versionada em data/sample."""
    filename = env("VIGIBARRAGENS_CSV") or "vigibarragens_barragens.csv"
    candidates = [
        APP_CONFIG.input_dir / filename,
        ROOT / "data" / "input" / "vigibarragens_barragens.csv",
        ROOT / "data" / "sample" / "vigibarragens_barragens.csv",
    ]
    for path in candidates:
        try:
            if path.exists():
                df = read_table_safe(path)
                if not df.empty:
                    return normalize_cols(df)
        except Exception as exc:
            log.warning("Falha ao ler CSV VigiBarragens %s: %s", path, exc)
    return pd.DataFrame()


def vigibarragens_risco_municipal(barragens: pd.DataFrame) -> pd.DataFrame:
    """Agrega o cadastro por município: exposição na ZAS e nível operacional SIS.

    O nível SIS municipal é o pior nível de emergência entre as barragens do
    município; barragens sem emergência mas com DPA Alto sobem para amarela
    (atenção/monitoramento).
    """
    if barragens is None or barragens.empty:
        return pd.DataFrame(
            columns=[
                "cod_ibge",
                "municipio",
                "uf",
                "n_barragens",
                "n_cri_alto",
                "n_dpa_alto",
                "n_em_emergencia",
                "populacao_zas_total",
                "nivel_emergencia_max",
                "nivel_sis",
                "motivo",
                "fonte",
                "data_processamento",
            ]
        )

    df = barragens.copy()
    for c in ["categoria_risco", "dano_potencial"]:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()
    if "nivel_emergencia_sis" not in df.columns:
        df["nivel_emergencia_sis"] = df.get("nivel_emergencia", "").map(_norm_nivel_emergencia)
    df["_ne_score"] = df["nivel_emergencia_sis"].map(_ORDER).fillna(0)
    df["populacao_zas"] = pd.to_numeric(df.get("populacao_zas"), errors="coerce")
    df["_cri_alto"] = df.get("categoria_risco", pd.Series([""] * len(df))).astype(str).str.lower().str.contains("alto", na=False)
    df["_dpa_alto"] = df.get("dano_potencial", pd.Series([""] * len(df))).astype(str).str.lower().str.contains("alto", na=False)

    keys = [c for c in ["cod_ibge", "municipio", "uf"] if c in df.columns]
    if not [c for c in ["cod_ibge", "municipio"] if c in df.columns]:
        return pd.DataFrame()

    rows: list[dict] = []
    for key_vals, g in df.groupby(keys, dropna=False):
        if not isinstance(key_vals, tuple):
            key_vals = (key_vals,)
        meta = dict(zip(keys, key_vals))
        ne_score = float(g["_ne_score"].max())
        nivel_por_emergencia = next((k for k, v in _ORDER.items() if v == int(ne_score)), "verde")
        n_dpa_alto = int(g["_dpa_alto"].sum())
        n_cri_alto = int(g["_cri_alto"].sum())
        n_emerg = int((g["_ne_score"] >= 2).sum())
        # Sem emergência declarada, mas DPA Alto → atenção (amarela).
        nivel_sis = nivel_por_emergencia
        if nivel_sis == "verde" and n_dpa_alto > 0:
            nivel_sis = "amarela"

        motivos = [f"{len(g)} barragem(ns) monitorada(s) (VigiBarragens/SIGBM)"]
        if n_emerg > 0:
            piores = g.sort_values("_ne_score", ascending=False)
            nome = str(piores.iloc[0].get("nome_barragem") or "barragem")
            motivos.append(f"Emergência {piores.iloc[0].get('nivel_emergencia')} em {nome}")
        if n_dpa_alto > 0:
            motivos.append(f"{n_dpa_alto} com Dano Potencial Alto")
        if n_cri_alto > 0:
            motivos.append(f"{n_cri_alto} com Categoria de Risco Alta")

        rows.append(
            {
                **meta,
                "n_barragens": int(len(g)),
                "n_cri_alto": n_cri_alto,
                "n_dpa_alto": n_dpa_alto,
                "n_em_emergencia": n_emerg,
                "populacao_zas_total": float(g["populacao_zas"].fillna(0).sum()),
                "nivel_emergencia_max": nivel_por_emergencia,
                "nivel_sis": nivel_sis,
                "motivo": "; ".join(motivos),
                "fonte": "VigiBarragens/SIGBM",
                "data_processamento": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    out = pd.DataFrame(rows)
    return out.sort_values("populacao_zas_total", ascending=False).reset_index(drop=True)


def barragens_alerta_for_municipio(
    risco: pd.DataFrame,
    municipio: str | None = None,
    cod_ibge: str | None = None,
) -> tuple[str | None, str | None]:
    """Retorna (motivo, nivel_sis) da exposição VigiBarragens do município."""
    if risco is None or risco.empty:
        return None, None

    df = risco
    selected = pd.DataFrame()
    if cod_ibge and "cod_ibge" in df.columns:
        cod = str(cod_ibge).strip()
        m = df["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False).eq(cod)
        selected = df.loc[m]
    if selected.empty and municipio and "municipio" in df.columns:
        selected = df[df["municipio"].astype(str).str.lower().eq(str(municipio).lower())]
    if selected.empty:
        return None, None

    selected = selected.copy()
    selected["_score"] = selected["nivel_sis"].map(_ORDER).fillna(0)
    row = selected.sort_values("_score", ascending=False).iloc[0]
    nivel = str(row.get("nivel_sis") or "verde")
    if nivel in {"verde", "cinza"}:
        return None, None
    pop = row.get("populacao_zas_total")
    motivo = f"VigiBarragens: {row.get('motivo') or 'exposição a barragem'}"
    if pd.notna(pop) and float(pop) > 0:
        motivo += f" · ~{int(float(pop))} hab. na ZAS"
    return motivo, nivel


def load_vigibarragens_bundle(municipios: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    """Carrega inventário de barragens (online → CSV) e o agregado municipal."""
    if not as_bool(env("USE_VIGIBARRAGENS", "true"), True):
        return {
            "vigibarragens_barragens": pd.DataFrame(columns=_BARRAGENS_COLS),
            "vigibarragens_exposicao_municipal": vigibarragens_risco_municipal(pd.DataFrame()),
        }

    barragens = normalize_barragens(fetch_vigibarragens_barragens())
    if barragens.empty:
        barragens = normalize_barragens(load_vigibarragens_csv_fallback())
        if not barragens.empty:
            log.info("VigiBarragens via CSV fallback: %s barragens", len(barragens))

    # Completa municipio a partir do cadastro IBGE quando faltar.
    if not barragens.empty and municipios is not None and not municipios.empty and "cod_ibge" in barragens.columns:
        need_name = barragens["municipio"].isna() | barragens["municipio"].astype(str).str.len().eq(0)
        if need_name.any() and "municipio" in municipios.columns:
            ref = municipios.copy()
            ref["cod_ibge"] = ref["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
            mapa = dict(zip(ref["cod_ibge"], ref["municipio"]))
            barragens.loc[need_name, "municipio"] = barragens.loc[need_name, "cod_ibge"].map(mapa)

    risco = vigibarragens_risco_municipal(barragens)
    return {
        "vigibarragens_barragens": barragens,
        "vigibarragens_exposicao_municipal": risco,
    }
