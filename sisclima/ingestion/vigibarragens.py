# -*- coding: utf-8 -*-
"""Populações vulneráveis geolocalizadas (Vigibarragens / VSR) para o ARARAS MT.

Lê CSVs tratados do projeto-irmão; não copia GeoJSON grande para o git.
Agrega por IBGE-7 e persiste tabelas enxutas no banco operacional.

Fontes:
- FUNAI WFS: aldeias (lat/lon + IBGE)
- Fundação Palmares: comunidades quilombolas certificadas
- INCRA: assentamentos (famílias; município por nome)
- SNISB/SIGBM: barragens (DPA, população a jusante declarada)
- Exposição eixo Manso–Cuiabá: coordenadas extras (quilombo/assentamento)

Aviso: distância ao eixo hidroelétrico não é polígono de inundação (ZAS/ZSS).
"""
from __future__ import annotations

import unicodedata
from functools import lru_cache
from pathlib import Path

import pandas as pd

from sisclima.core.config import ROOT, env
from sisclima.core.db import write_df
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

_DEFAULT_SISTER = Path.home() / "OneDrive" / "Projeto VSR" / "barragens-mt" / "dados" / "tratados"
_CACHE_DIR = ROOT / "data" / "local" / "vigibarragens"

CATEGORIA_ALDEIA = "aldeia indígena"
CATEGORIA_QUILOMBO = "quilombo"
CATEGORIA_ASSENTAMENTO = "assentamento"
CATEGORIA_TI = "terra indígena"
CATEGORIA_BARRAGEM = "barragem"


def data_dir() -> Path:
    raw = (env("VIGIBARRAGENS_DATA_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser()
    if _DEFAULT_SISTER.exists():
        return _DEFAULT_SISTER
    return ROOT / "data" / "input" / "vigibarragens"


def _cod7(s: pd.Series) -> pd.Series:
    raw = s.astype(str).str.replace(r"\.0$", "", regex=True).str.replace(r"\D", "", regex=True)
    return raw.str.extract(r"(\d{7})", expand=False)


_NOME_ALIAS = {
    "poxoreo": "poxoreu",
    "santoantoniodoleverger": "santoantoniodeleverger",
}


def _nome_chave(val) -> str:
    s = unicodedata.normalize("NFKD", str(val or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    chave = "".join(ch for ch in s.lower() if ch.isalnum())
    return _NOME_ALIAS.get(chave, chave)


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(",", ".", regex=False), errors="coerce")


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    last_err = None
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            head = path.read_bytes()[:2048]
            text = head.decode(enc, errors="replace")
            sep = ";" if text.count(";") > text.count(",") else ","
            return pd.read_csv(path, sep=sep, encoding=enc, dtype=str)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
    log.warning("Não leu %s: %s", path.name, last_err)
    return pd.DataFrame()


@lru_cache(maxsize=1)
def _catalogo() -> pd.DataFrame:
    try:
        from sisclima.ingestion.ibge_municipios import catalogo_municipios_mt

        cat = catalogo_municipios_mt()
    except Exception as exc:  # noqa: BLE001
        log.warning("Catálogo IBGE indisponível para Vigibarragens: %s", exc)
        return pd.DataFrame()
    if cat is None or cat.empty:
        return pd.DataFrame()
    out = cat.copy()
    out["cod_ibge"] = _cod7(out["cod_ibge"])
    out["municipio"] = out["municipio"].astype(str)
    out["mun_chave"] = out["municipio"].map(_nome_chave)
    return out.dropna(subset=["cod_ibge"]).drop_duplicates("cod_ibge")


def _join_nome(df: pd.DataFrame, col: str, cat: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["mun_chave"] = out[col].map(_nome_chave)
    if cat.empty:
        return out
    mapa = cat[["mun_chave", "cod_ibge", "municipio"]].drop_duplicates("mun_chave")
    if "cod_ibge" in out.columns and out["cod_ibge"].isna().all():
        out = out.drop(columns=["cod_ibge"])
    out = out.merge(mapa, on="mun_chave", how="left", suffixes=("", "_cat"))
    if "cod_ibge_cat" in out.columns:
        out["cod_ibge"] = out["cod_ibge"].fillna(out["cod_ibge_cat"])
        out = out.drop(columns=["cod_ibge_cat"])
    if "municipio_cat" in out.columns:
        out["municipio"] = out["municipio"].where(out["municipio"].astype(str).str.len() > 1, out["municipio_cat"])
        out = out.drop(columns=["municipio_cat"], errors="ignore")
    elif "municipio" not in out.columns and "municipio_raw" in out.columns:
        out["municipio"] = out["municipio_raw"]
    return out


def _pontos_base(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    out["lat"] = _num(out["lat"]) if "lat" in out.columns else pd.NA
    out["lon"] = _num(out["lon"]) if "lon" in out.columns else pd.NA
    out["familias"] = _num(out["familias"]) if "familias" in out.columns else pd.NA
    out["moradores"] = _num(out["moradores"]) if "moradores" in out.columns else pd.NA
    out["cod_ibge"] = _cod7(out["cod_ibge"]) if "cod_ibge" in out.columns else pd.NA
    ok = out["lat"].between(-25, -5) & out["lon"].between(-65, -49)
    out.loc[~ok.fillna(False), ["lat", "lon"]] = pd.NA
    return out


def _aldeias(pasta: Path, cat: pd.DataFrame) -> pd.DataFrame:
    raw = _read_csv(pasta / "funai_aldeias_mt.csv")
    if raw.empty:
        return pd.DataFrame()
    cols = {c.lower().strip(): c for c in raw.columns}
    rows = []
    for _, r in raw.iterrows():
        rows.append(
            {
                "categoria": CATEGORIA_ALDEIA,
                "nome": r.get(cols.get("nome_aldeia") or "nome_aldeia"),
                "cod_ibge": r.get(cols.get("cod_municipio") or "cod_municipio"),
                "municipio": r.get(cols.get("nommunic") or "nommunic"),
                "lat": r.get(cols.get("coord_lat") or "coord_lat"),
                "lon": r.get(cols.get("coord_long") or "coord_long"),
                "familias": None,
                "moradores": None,
                "detalhe": r.get(cols.get("cod_ti") or "cod_ti"),
                "fonte": "FUNAI/aldeias",
            }
        )
    out = _pontos_base(rows)
    if not cat.empty and "cod_ibge" in out.columns:
        nomes = cat.set_index("cod_ibge")["municipio"]
        out["municipio"] = out["cod_ibge"].map(nomes).fillna(out["municipio"])
    return out


def _quilombos(pasta: Path, cat: pd.DataFrame) -> pd.DataFrame:
    raw = _read_csv(pasta / "palmares_quilombolas_mt.csv")
    if raw.empty:
        return pd.DataFrame()
    cols = {unicodedata.normalize("NFKD", c).encode("ascii", "ignore").decode().lower().strip(): c for c in raw.columns}
    ibge_c = cols.get("codigo do ibge") or cols.get("codigo_ibge")
    nome_c = cols.get("comunidade")
    mun_c = cols.get("municipio")
    mor_c = cols.get("n de moradores") or cols.get("no de moradores")
    rows = []
    for _, r in raw.iterrows():
        rows.append(
            {
                "categoria": CATEGORIA_QUILOMBO,
                "nome": r.get(nome_c) if nome_c else None,
                "cod_ibge": r.get(ibge_c) if ibge_c else None,
                "municipio": r.get(mun_c) if mun_c else None,
                "lat": None,
                "lon": None,
                "familias": None,
                "moradores": r.get(mor_c) if mor_c else None,
                "detalhe": r.get(cols.get("urbana/rural")) if cols.get("urbana/rural") else None,
                "fonte": "Fundação Palmares",
            }
        )
    out = _pontos_base(rows)
    if not cat.empty:
        nomes = cat.set_index("cod_ibge")["municipio"]
        out["municipio"] = out["cod_ibge"].map(nomes).fillna(out["municipio"])
    return out


def _assentamentos(pasta: Path, cat: pd.DataFrame) -> pd.DataFrame:
    raw = _read_csv(pasta / "incra_assentamentos_mt.csv")
    if raw.empty:
        return pd.DataFrame()
    cols = {c.lower().strip(): c for c in raw.columns}
    work = pd.DataFrame(
        {
            "categoria": CATEGORIA_ASSENTAMENTO,
            "nome": raw.get(cols.get("nome_projeto") or "nome_projeto"),
            "municipio_raw": raw.get(cols.get("municipio") or "municipio"),
            "familias": raw.get(cols.get("num_familias") or "num_familias"),
            "moradores": None,
            "lat": None,
            "lon": None,
            "detalhe": raw.get(cols.get("cd_sipra") or "cd_sipra"),
            "fonte": "INCRA/SIPRA",
            "cod_ibge": None,
        }
    )
    work = _join_nome(work, "municipio_raw", cat)
    work["municipio"] = work.get("municipio", work["municipio_raw"])
    return _pontos_base(work.to_dict("records"))


def _terras_indigenas_municipal(pasta: Path, cat: pd.DataFrame) -> pd.DataFrame:
    raw = _read_csv(pasta / "funai_terras_indigenas_mt.csv")
    if raw.empty or cat.empty:
        return pd.DataFrame(columns=["cod_ibge", "n_terras_indigenas"])
    cols = {c.lower().strip(): c for c in raw.columns}
    mun_c = cols.get("municipio_nome")
    nome_c = cols.get("terrai_nome")
    rows = []
    for _, r in raw.iterrows():
        nomes = str(r.get(mun_c) or "")
        for parte in nomes.split(","):
            rows.append({"municipio_raw": parte.strip(), "nome": r.get(nome_c)})
    work = pd.DataFrame(rows)
    if work.empty:
        return pd.DataFrame(columns=["cod_ibge", "n_terras_indigenas"])
    work = _join_nome(work, "municipio_raw", cat)
    g = work.dropna(subset=["cod_ibge"]).groupby("cod_ibge", as_index=False).agg(n_terras_indigenas=("nome", "nunique"))
    return g


_EXP_CAT = {
    "assentamentorural": CATEGORIA_ASSENTAMENTO,
    "assentamento": CATEGORIA_ASSENTAMENTO,
    "territorioquilombola": CATEGORIA_QUILOMBO,
    "quilombo": CATEGORIA_QUILOMBO,
}


def _coords_exposicao(pasta: Path) -> pd.DataFrame:
    """Completa lat/lon de quilombos e assentamentos a partir da planilha de exposição."""
    raw = _read_csv(pasta / "exposicao_populacoes_eixo_cuiaba.csv")
    if raw.empty:
        return pd.DataFrame()
    cols = {c.lower().strip(): c for c in raw.columns}
    cat_c = cols.get("categoria")
    if not cat_c:
        return pd.DataFrame()
    cat_norm = raw[cat_c].map(_nome_chave).map(_EXP_CAT)
    keep = raw[cat_norm.notna()].copy()
    if keep.empty:
        return pd.DataFrame()
    out = pd.DataFrame(
        {
            "categoria": cat_norm.loc[keep.index],
            "nome": keep[cols.get("nome")].astype(str) if cols.get("nome") else "",
            "municipio": keep[cols.get("municipio")] if cols.get("municipio") else None,
            "lat": keep[cols.get("latitude")] if cols.get("latitude") else None,
            "lon": keep[cols.get("longitude")] if cols.get("longitude") else None,
        }
    )
    out["chave"] = out["categoria"] + "|" + out["nome"].map(_nome_chave)
    out["lat"] = _num(out["lat"])
    out["lon"] = _num(out["lon"])
    return out.dropna(subset=["lat", "lon"]).drop_duplicates("chave")


def _completar_coords(pontos: pd.DataFrame, extra: pd.DataFrame) -> pd.DataFrame:
    if pontos.empty or extra.empty:
        return pontos
    out = pontos.copy()
    out["chave"] = out["categoria"].astype(str).str.lower() + "|" + out["nome"].map(_nome_chave)
    mapa = extra.set_index("chave")[["lat", "lon"]]
    miss = out["lat"].isna() | out["lon"].isna()
    fill_lat = out.loc[miss, "chave"].map(mapa["lat"])
    fill_lon = out.loc[miss, "chave"].map(mapa["lon"])
    out.loc[miss, "lat"] = out.loc[miss, "lat"].fillna(fill_lat)
    out.loc[miss, "lon"] = out.loc[miss, "lon"].fillna(fill_lon)
    return out.drop(columns=["chave"], errors="ignore")


def _barragens_municipal(pasta: Path) -> pd.DataFrame:
    raw = _read_csv(pasta / "inventario_barragens_mt.csv")
    if raw.empty:
        return pd.DataFrame(columns=["cod_ibge", "n_barragens", "n_barragens_dpa_alto", "pop_jusante_sigbm"])
    cols = {c.lower().strip(): c for c in raw.columns}
    ibge_c = cols.get("codigo_ibge")
    dpa_c = cols.get("dano_potencial_associado")
    pop_c = cols.get("sigbm_populacao_jusante")
    work = pd.DataFrame(
        {
            "cod_ibge": _cod7(raw[ibge_c]) if ibge_c else pd.NA,
            "dpa": raw[dpa_c].astype(str).str.lower() if dpa_c else "",
            "pop_jusante": _num(raw[pop_c]) if pop_c else pd.NA,
        }
    )
    work = work.dropna(subset=["cod_ibge"])
    g = work.groupby("cod_ibge", as_index=False).agg(
        n_barragens=("cod_ibge", "size"),
        n_barragens_dpa_alto=("dpa", lambda s: int(s.str.contains(r"alto", regex=True, na=False).sum())),
        pop_jusante_sigbm=("pop_jusante", "sum"),
    )
    return g


def load_pontos(pasta: Path | None = None) -> pd.DataFrame:
    pasta = pasta or data_dir()
    cat = _catalogo()
    partes = [_aldeias(pasta, cat), _quilombos(pasta, cat), _assentamentos(pasta, cat)]
    pontos = pd.concat([p for p in partes if p is not None and not p.empty], ignore_index=True)
    if pontos.empty:
        log.warning("Vigibarragens: nenhum ponto em %s", pasta)
        return pontos
    pontos = _completar_coords(pontos, _coords_exposicao(pasta))
    pontos["cod_ibge"] = _cod7(pontos["cod_ibge"])
    return pontos


def agregar_municipal(pontos: pd.DataFrame | None = None, pasta: Path | None = None) -> pd.DataFrame:
    pasta = pasta or data_dir()
    pontos = pontos if pontos is not None else load_pontos(pasta)
    cat = _catalogo()
    if cat.empty:
        base = pd.DataFrame(columns=["cod_ibge", "municipio"])
    else:
        base = cat[["cod_ibge", "municipio"]].drop_duplicates("cod_ibge")

    def _n(cat_name: str) -> pd.Series:
        if pontos is None or pontos.empty:
            return pd.Series(dtype="int64")
        m = pontos[pontos["categoria"].astype(str).str.lower() == cat_name]
        return m.dropna(subset=["cod_ibge"]).groupby("cod_ibge").size()

    def _sum(cat_name: str, col: str) -> pd.Series:
        if pontos is None or pontos.empty or col not in pontos.columns:
            return pd.Series(dtype="float64")
        m = pontos[pontos["categoria"].astype(str).str.lower() == cat_name]
        return pd.to_numeric(m.dropna(subset=["cod_ibge"]).groupby("cod_ibge")[col].sum(), errors="coerce")

    out = base.copy()
    out["n_aldeias"] = out["cod_ibge"].map(_n(CATEGORIA_ALDEIA)).fillna(0).astype(int)
    out["n_quilombos"] = out["cod_ibge"].map(_n(CATEGORIA_QUILOMBO)).fillna(0).astype(int)
    out["n_assentamentos"] = out["cod_ibge"].map(_n(CATEGORIA_ASSENTAMENTO)).fillna(0).astype(int)
    out["familias_assentamentos"] = out["cod_ibge"].map(_sum(CATEGORIA_ASSENTAMENTO, "familias")).fillna(0)
    out["moradores_quilombo"] = out["cod_ibge"].map(_sum(CATEGORIA_QUILOMBO, "moradores")).fillna(0)
    tis = _terras_indigenas_municipal(pasta, cat)
    if not tis.empty:
        out = out.merge(tis, on="cod_ibge", how="left")
    out["n_terras_indigenas"] = pd.to_numeric(out.get("n_terras_indigenas"), errors="coerce").fillna(0).astype(int)
    bar = _barragens_municipal(pasta)
    if not bar.empty:
        out = out.merge(bar, on="cod_ibge", how="left")
    for c in ("n_barragens", "n_barragens_dpa_alto"):
        out[c] = pd.to_numeric(out.get(c), errors="coerce").fillna(0).astype(int)
    out["pop_jusante_sigbm"] = pd.to_numeric(out.get("pop_jusante_sigbm"), errors="coerce").fillna(0)
    out["n_territorios_tradicionais"] = out["n_aldeias"] + out["n_quilombos"] + out["n_assentamentos"]
    out["tem_territorio_tradicional"] = (out["n_territorios_tradicionais"] > 0).astype(int)
    out["tem_zas_barragem"] = (out["n_barragens_dpa_alto"] > 0).astype(int)
    return out


def persistir(pasta: Path | None = None) -> dict:
    pasta = pasta or data_dir()
    pontos = load_pontos(pasta)
    mun = agregar_municipal(pontos, pasta)
    write_df(pontos, "vigibarragens_populacoes")
    write_df(mun, "vigibarragens_municipal")
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not pontos.empty:
        pontos.to_csv(_CACHE_DIR / "pontos.csv", index=False, encoding="utf-8-sig")
    if not mun.empty:
        mun.to_csv(_CACHE_DIR / "municipal.csv", index=False, encoding="utf-8-sig")
    log.info(
        "Vigibarragens: %s pontos, %s municípios com território tradicional, pasta=%s",
        0 if pontos.empty else len(pontos),
        int((mun["tem_territorio_tradicional"] == 1).sum()) if not mun.empty else 0,
        pasta,
    )
    return {
        "ok": not pontos.empty or not mun.empty,
        "pontos": 0 if pontos.empty else len(pontos),
        "municipios_territorio": int((mun["tem_territorio_tradicional"] == 1).sum()) if not mun.empty else 0,
        "pasta": str(pasta),
        "pontos_df": pontos,
        "municipal_df": mun,
    }
