# -*- coding: utf-8 -*-
"""Regionais de Saúde SES-MT (16 ERS / CRS) no recorte IBGE de 142 municípios.

Fonte: Decreto 2.327/2014 (COGIS/SUPS/SES-MT) + CIB/MT 57/2018 (6 macrorregiões).
Boa Esperança do Norte (5101837) herda a CRS de Nova Ubiratã (Sinop).
"""
from __future__ import annotations

import unicodedata
from pathlib import Path

import pandas as pd

from sisclima.core.config import APP_CONFIG
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

REGIONAIS_CSV = APP_CONFIG.root / "config" / "regionais_saude_mt.csv"

# ERS / CRS e macrorregião CIB. Municípios pelo nome IBGE (aliases no _norm).
_ERS: list[tuple[str, str, list[str]]] = [
    (
        "Baixada Cuiabana",
        "Centro",
        [
            "Cuiabá", "Acorizal", "Barão de Melgaço", "Chapada dos Guimarães", "Jangada",
            "Nossa Senhora do Livramento", "Nova Brasilândia", "Planalto da Serra", "Poconé",
            "Santo Antônio de Leverger", "Várzea Grande",
        ],
    ),
    (
        "Rondonópolis",
        "Sul",
        [
            "Rondonópolis", "Alto Araguaia", "Alto Garças", "Alto Taquari", "Araguainha",
            "Campo Verde", "Dom Aquino", "Guiratinga", "Itiquira", "Jaciara", "Juscimeira",
            "Paranatinga", "Pedra Preta", "Poxoréu", "Primavera do Leste",
            "Santo Antônio do Leste", "São José do Povo", "São Pedro da Cipa", "Tesouro",
        ],
    ),
    (
        "Barra do Garças",
        "Leste",
        [
            "Barra do Garças", "Araguaiana", "Campinápolis", "General Carneiro",
            "Nova Xavantina", "Novo São Joaquim", "Pontal do Araguaia", "Ponte Branca",
            "Ribeirãozinho", "Torixoréu",
        ],
    ),
    (
        "Cáceres",
        "Oeste",
        [
            "Cáceres", "Araputanga", "Curvelândia", "Glória D'Oeste", "Indiavaí",
            "Lambari D'Oeste", "Mirassol d'Oeste", "Porto Esperidião", "Reserva do Cabaçal",
            "Rio Branco", "Salto do Céu", "São José dos Quatro Marcos",
        ],
    ),
    (
        "Juína",
        "Noroeste e Médio Norte",
        ["Juína", "Aripuanã", "Brasnorte", "Castanheira", "Colniza", "Cotriguaçu", "Juruena"],
    ),
    (
        "Porto Alegre do Norte",
        "Leste",
        [
            "Porto Alegre do Norte", "Canabrava do Norte", "Confresa", "Santa Cruz do Xingu",
            "Santa Terezinha", "São José do Xingu", "Vila Rica",
        ],
    ),
    (
        "Sinop",
        "Norte",
        [
            "Sinop", "Cláudia", "Feliz Natal", "Ipiranga do Norte", "Itanhangá",
            "Lucas do Rio Verde", "Nova Mutum", "Nova Ubiratã", "Boa Esperança do Norte",
            "Santa Carmem", "Santa Rita do Trivelato", "Sorriso", "Tapurah", "União do Sul", "Vera",
        ],
    ),
    (
        "Tangará da Serra",
        "Noroeste e Médio Norte",
        [
            "Tangará da Serra", "Arenápolis", "Barra do Bugres", "Campo Novo do Parecis",
            "Denise", "Nova Marilândia", "Nova Olímpia", "Porto Estrela", "Santo Afonso", "Sapezal",
        ],
    ),
    (
        "Diamantino",
        "Centro",
        [
            "Diamantino", "Alto Paraguai", "Nobres", "Nortelândia", "Nova Maringá",
            "Rosário Oeste", "São José do Rio Claro",
        ],
    ),
    (
        "Alta Floresta",
        "Norte",
        ["Alta Floresta", "Apiacás", "Carlinda", "Nova Bandeirantes", "Nova Monte Verde", "Paranaíta"],
    ),
    (
        "Juara",
        "Norte",
        ["Juara", "Novo Horizonte do Norte", "Porto dos Gaúchos", "Tabaporã"],
    ),
    (
        "Peixoto de Azevedo",
        "Norte",
        ["Peixoto de Azevedo", "Guarantã do Norte", "Matupá", "Novo Mundo", "Terra Nova do Norte"],
    ),
    (
        "Água Boa",
        "Leste",
        [
            "Água Boa", "Bom Jesus do Araguaia", "Canarana", "Cocalinho", "Gaúcha do Norte",
            "Nova Nazaré", "Querência", "Ribeirão Cascalheira",
        ],
    ),
    (
        "Pontes e Lacerda",
        "Oeste",
        [
            "Pontes e Lacerda", "Campos de Júlio", "Comodoro", "Conquista D'Oeste",
            "Figueirópolis D'Oeste", "Jauru", "Nova Lacerda", "Rondolândia",
            "Vale de São Domingos", "Vila Bela da Santíssima Trindade",
        ],
    ),
    (
        "Colíder",
        "Norte",
        ["Colíder", "Itaúba", "Marcelândia", "Nova Canaã do Norte", "Nova Guarita", "Nova Santa Helena"],
    ),
    (
        "São Félix do Araguaia",
        "Leste",
        [
            "São Félix do Araguaia", "Alto Boa Vista", "Luciara", "Novo Santo Antônio",
            "Serra Nova Dourada",
        ],
    ),
]

_ALIAS_NORM = {
    "poxoreo": "poxoreu",
    "santo antonio do leverger": "santo antonio de leverger",
    "santo antonio do leverguer": "santo antonio de leverger",
    "gloria d oeste": "gloria doeste",
    "conquista d oeste": "conquista doeste",
    "figueiropolis d oeste": "figueiropolis doeste",
    "lambari d oeste": "lambari doeste",
    "mirassol d oeste": "mirassol doeste",
    "mirassol do oeste": "mirassol doeste",
}


def _norm_mun(nome: str) -> str:
    raw = unicodedata.normalize("NFKD", str(nome or ""))
    ascii_ = raw.encode("ascii", "ignore").decode("ascii")
    s = " ".join(ascii_.lower().replace("'", " ").replace("-", " ").split())
    s = s.replace(" d ", " d")
    return _ALIAS_NORM.get(s, s)


def _lookup() -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for regional, macro, municipios in _ERS:
        for nome in municipios:
            out[_norm_mun(nome)] = (regional, macro)
    return out


def catalogo_regionais_ses() -> pd.DataFrame:
    """Catálogo município → CRS SES (CSV; gera na 1ª carga se faltar)."""
    path = Path(REGIONAIS_CSV)
    if path.exists():
        df = pd.read_csv(path, dtype={"cod_ibge": str})
        if not df.empty and {"cod_ibge", "regional_saude"}.issubset(df.columns):
            df["cod_ibge"] = df["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
            return df.dropna(subset=["cod_ibge"]).drop_duplicates("cod_ibge")
    return gerar_catalogo_regionais_ses(path)


def gerar_catalogo_regionais_ses(path: Path | None = None) -> pd.DataFrame:
    from sisclima.ingestion.ibge_municipios import catalogo_municipios_mt

    cat = catalogo_municipios_mt()
    if cat is None or cat.empty:
        return pd.DataFrame()
    look = _lookup()
    rows = []
    miss = []
    for _, row in cat.iterrows():
        nome = str(row.get("municipio") or "")
        key = _norm_mun(nome)
        hit = look.get(key)
        if hit is None:
            miss.append(nome)
            regional, macro = "Regional não informada", ""
        else:
            regional, macro = hit
        rows.append(
            {
                "cod_ibge": pd.Series([row["cod_ibge"]]).astype(str).str.extract(r"(\d{7})", expand=False).iloc[0],
                "municipio": nome,
                "regional_saude": regional,
                "macroregiao_saude": macro,
            }
        )
    out = pd.DataFrame(rows)
    if miss:
        log.warning("Sem CRS SES para %s município(s): %s", len(miss), ", ".join(miss[:12]))
    dest = Path(path or REGIONAIS_CSV)
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(dest, index=False, encoding="utf-8")
    log.info("Catálogo CRS SES gravado em %s (%s mun, %s regionais).", dest, len(out), out["regional_saude"].nunique())
    return out


def aplicar_regionais_ses(df: pd.DataFrame) -> pd.DataFrame:
    """Sobrescreve regional_saude / macroregiao_saude com o recorte SES-MT."""
    if df is None or df.empty or "cod_ibge" not in df.columns:
        return df if df is not None else pd.DataFrame()
    cat = catalogo_regionais_ses()
    if cat is None or cat.empty:
        return df
    out = df.copy()
    out["cod_ibge"] = out["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
    inj = cat[["cod_ibge", "regional_saude", "macroregiao_saude"]].drop_duplicates("cod_ibge")
    inj = inj.rename(columns={"regional_saude": "_rs_ses", "macroregiao_saude": "_macro_ses"})
    out = out.merge(inj, on="cod_ibge", how="left")
    ses_ok = out["_rs_ses"].notna() & ~out["_rs_ses"].astype(str).str.strip().str.lower().isin(
        {"", "nan", "none", "regional não informada", "regional nao informada"}
    )
    if "regional_saude" in out.columns:
        out.loc[ses_ok, "regional_saude"] = out.loc[ses_ok, "_rs_ses"]
        out["regional_saude"] = out["regional_saude"].combine_first(out["_rs_ses"])
    else:
        out["regional_saude"] = out["_rs_ses"]
    if "macroregiao_saude" in out.columns:
        out.loc[out["_macro_ses"].notna(), "macroregiao_saude"] = out.loc[out["_macro_ses"].notna(), "_macro_ses"]
        out["macroregiao_saude"] = out["macroregiao_saude"].combine_first(out["_macro_ses"])
    else:
        out["macroregiao_saude"] = out["_macro_ses"]
    return out.drop(columns=["_rs_ses", "_macro_ses"], errors="ignore")
