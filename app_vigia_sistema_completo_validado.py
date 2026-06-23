# -*- coding: utf-8 -*-
"""
VIGIA Clima-Saúde MT — Painel completo cloud validado.

Correções aplicadas:
- Usa exclusivamente data/public.
- Sumário Executivo por cor de risco.
- GeoJSON municipal por cod_ibge.
- GeoCalor Cuiabá com fallback: geocalor_cuiaba_cardioresp_v11_12.csv ou geocalor_cardioresp_rr_municipal_v11_12.csv filtrado por Cuiabá.
- Bases auxiliares com filtro municipal robusto por município, cod_ibge ou fallback sem erro.
"""

from __future__ import annotations

from pathlib import Path
import json
import re
import unicodedata

import pandas as pd
import plotly.express as px
import streamlit as st


BASE = Path(__file__).parent
PUBLIC = BASE / "data" / "public"
CENTER_MT = {"lat": -12.8, "lon": -55.8}

CORES = {
    "verde": "#2E8B57",
    "amarela": "#D4A719",
    "laranja": "#F47C20",
    "vermelha": "#D83232",
    "roxa": "#7E22CE",
    "cinza": "#6B7280",
}
ORDEM = {"cinza": 0, "verde": 1, "amarela": 2, "laranja": 3, "vermelha": 4, "roxa": 5}


def norm_text(x) -> str:
    if x is None or pd.isna(x):
        return ""
    s = str(x).strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def normalize_level(value) -> str:
    s = norm_text(value)
    mapping = {
        "verde": "verde", "monitoramento": "verde", "normal": "verde",
        "amarelo": "amarela", "amarela": "amarela", "atencao": "amarela",
        "laranja": "laranja", "alto": "laranja",
        "vermelho": "vermelha", "vermelha": "vermelha", "critico": "vermelha",
        "roxo": "roxa", "roxa": "roxa",
        "cinza": "cinza", "sem dado": "cinza", "sem dados": "cinza",
    }
    return mapping.get(s, "cinza")


def detect_col(df: pd.DataFrame, options: list[str]) -> str | None:
    if df.empty:
        return None
    lookup = {norm_text(c): c for c in df.columns}
    for o in options:
        key = norm_text(o)
        if key in lookup:
            return lookup[key]
    return None


@st.cache_data(show_spinner=False)
def load_csv(name: str) -> pd.DataFrame:
    path = PUBLIC / name
    if not path.exists():
        return pd.DataFrame()
    for enc in ["utf-8-sig", "utf-8", "latin1"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            continue
    try:
        return pd.read_csv(path)
    except Exception as exc:
        st.warning(f"Erro ao ler {name}: {exc}")
        return pd.DataFrame()


@st.cache_data(show_spinner=False)
def load_geojson() -> dict | None:
    for name in ["municipios_mt_2025_simplificado.geojson", "municipios_mt_2025.geojson"]:
        path = PUBLIC / name
        if not path.exists():
            continue
        try:
            geo = json.loads(path.read_text(encoding="utf-8"))
            for feat in geo.get("features", []):
                props = feat.setdefault("properties", {})
                cod = None
                for key in ["cod_ibge", "CD_MUN", "CD_GEOCMU", "CD_MUNGE", "codigo_ibge", "ibge"]:
                    if key in props:
                        m = re.search(r"(\d{6,7})", str(props.get(key)))
                        if m:
                            cod = m.group(1)
                            break
                if cod:
                    props["cod_ibge"] = cod
            return geo
        except Exception:
            continue
    return None


def fmt(v, suffix="", digits=1):
    try:
        if v is None or pd.isna(v):
            return "—"
        return f"{float(v):,.{digits}f}{suffix}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "—"


def metric(df: pd.DataFrame, cols: list[str], agg="max"):
    col = detect_col(df, cols)
    if not col:
        return None
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    if s.empty:
        return None
    if agg == "mean":
        return float(s.mean())
    if agg == "sum":
        return float(s.sum())
    return float(s.max())


def prepare_resumo():
    df = load_csv("resumo_municipal_atual.csv")
    cols = {
        "municipio": detect_col(df, ["municipio", "Município", "nome_municipio"]),
        "regional": detect_col(df, ["regional_saude", "regional", "regiao_saude"]),
        "nivel": detect_col(df, ["nivel_operacional", "nivel", "alerta_nivel", "estagio"]),
        "cod_ibge": detect_col(df, ["cod_ibge", "ibge", "codigo_ibge", "cod_mun"]),
    }
    if not df.empty:
        if cols["nivel"]:
            df["nivel_norm"] = df[cols["nivel"]].apply(normalize_level)
        else:
            df["nivel_norm"] = "cinza"
        if cols["municipio"]:
            df["municipio_norm"] = df[cols["municipio"]].astype(str).map(norm_text)
        if cols["cod_ibge"]:
            df[cols["cod_ibge"]] = df[cols["cod_ibge"]].astype(str).str.extract(r"(\d{6,7})", expand=False)
    return df, cols


def filter_global(df, cols, municipios, regionais):
    out = df.copy()
    if cols.get("regional") and regionais:
        out = out[out[cols["regional"]].astype(str).isin(regionais)]
    if cols.get("municipio") and municipios:
        out = out[out[cols["municipio"]].astype(str).isin(municipios)]
    return out


def pending(title, message):
    st.markdown(
        f"<div style='border-left:6px solid #D4A719;background:#FFF7DB;padding:12px 14px;border-radius:10px'>"
        f"<b>{title}</b><br>{message}</div>",
        unsafe_allow_html=True,
    )


def map_layer(df, cols, color_col, title, discrete=True):
    geo = load_geojson()
    cod = cols.get("cod_ibge") or detect_col(df, ["cod_ibge", "ibge", "codigo_ibge"])
    mun = cols.get("municipio") or detect_col(df, ["municipio", "Município", "nome_municipio"])
    if df.empty:
        st.info("Sem dados para mapa.")
        return
    if not geo or not cod or cod not in df.columns:
        st.info("GeoJSON ou cod_ibge ausente. Exibindo tabela.")
        st.dataframe(df, use_container_width=True, hide_index=True)
        return
    tmp = df.copy()
    tmp[cod] = tmp[cod].astype(str).str.extract(r"(\d{6,7})", expand=False)
    tmp = tmp[tmp[cod].notna()]
    try:
        kwargs = dict(
            geojson=geo, locations=cod, featureidkey="properties.cod_ibge",
            color=color_col, hover_name=mun if mun else None,
            zoom=4.7, center=CENTER_MT, height=620, title=title
        )
        if hasattr(px, "choropleth_map"):
            fig = px.choropleth_map(tmp, map_style="carto-positron", color_discrete_map=CORES if discrete else None, **kwargs)
        else:
            fig = px.choropleth_mapbox(tmp, mapbox_style="carto-positron", color_discrete_map=CORES if discrete else None, **kwargs)
        fig.update_layout(margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(fig, use_container_width=True)
    except Exception as exc:
        st.warning(f"Falha ao renderizar mapa: {exc}")
        st.dataframe(tmp, use_container_width=True, hide_index=True)


def filter_for_municipio(df: pd.DataFrame, municipio: str | None, cod_ibge: str | None = None) -> tuple[pd.DataFrame, str]:
    if df.empty:
        return df, "fonte ausente"

    mun_col = detect_col(df, ["municipio", "Município", "nome_municipio", "municipio_nome"])
    if mun_col:
        out = df[df[mun_col].astype(str).map(norm_text).eq(norm_text(municipio))].copy()
        if not out.empty:
            return out, f"filtrado por {mun_col}"
        return df, f"coluna {mun_col} existe, mas sem registro para {municipio}; exibindo base completa"

    cod_col = detect_col(df, ["cod_ibge", "ibge", "codigo_ibge", "cod_mun"])
    if cod_col and cod_ibge:
        cod = re.search(r"(\d{6,7})", str(cod_ibge))
        if cod:
            out = df[df[cod_col].astype(str).str.contains(cod.group(1), na=False)].copy()
            if not out.empty:
                return out, f"filtrado por {cod_col}"

    return df, "sem coluna municipal identificável; exibindo base completa validada"


def load_geocalor_cuiaba() -> tuple[pd.DataFrame, str]:
    direct = load_csv("geocalor_cuiaba_cardioresp_v11_12.csv")
    if not direct.empty:
        return direct, "geocalor_cuiaba_cardioresp_v11_12.csv"

    rr = load_csv("geocalor_cardioresp_rr_municipal_v11_12.csv")
    if not rr.empty:
        mun = detect_col(rr, ["municipio", "Município", "nome_municipio"])
        cod = detect_col(rr, ["cod_ibge", "ibge", "codigo_ibge"])
        out = pd.DataFrame()
        if mun:
            out = rr[rr[mun].astype(str).map(norm_text).eq("cuiaba")].copy()
        if out.empty and cod:
            out = rr[rr[cod].astype(str).str.contains("5103403", na=False)].copy()
        if not out.empty:
            return out, "fallback geocalor_cardioresp_rr_municipal_v11_12.csv filtrado para Cuiabá"
    return pd.DataFrame(), "GeoCalor Cuiabá não publicado em data/public"


def indicator_catalog(bases: dict[str, pd.DataFrame]):
    rows = []
    for name, df in bases.items():
        if df.empty:
            rows.append({"base": name, "indicador": "—", "status": "PENDENTE", "preenchidos": 0, "total": 0})
        else:
            for c in df.columns:
                rows.append({"base": name, "indicador": c, "status": "DISPONIVEL" if df[c].notna().sum() else "VAZIO", "preenchidos": int(df[c].notna().sum()), "total": len(df)})
    return pd.DataFrame(rows)


st.set_page_config(page_title="VIGIA Clima-Saúde MT", page_icon="🌡️", layout="wide")

st.markdown("""
<style>
.main .block-container {padding-top:1.1rem;}
.vigia-header {background:linear-gradient(135deg,#0f172a,#164e63,#166534);color:white;padding:22px 28px;border-radius:18px;margin-bottom:16px}
.vigia-title {font-size:2rem;font-weight:800}
.vigia-subtitle {opacity:.95}
</style>
<div class="vigia-header">
<div class="vigia-title">VIGIA Clima-Saúde MT</div>
<div class="vigia-subtitle">Vigilância Integrada de Gestão, Inteligência e Alertas em Clima e Saúde</div>
</div>
""", unsafe_allow_html=True)

resumo, cols = prepare_resumo()
if resumo.empty:
    st.error("Arquivo obrigatório ausente ou vazio: data/public/resumo_municipal_atual.csv")
    st.stop()

with st.sidebar:
    st.header("Filtros")
    regionais = []
    municipios = []
    if cols["regional"]:
        regionais = st.multiselect("Regional", sorted(resumo[cols["regional"]].dropna().astype(str).unique()))
    if cols["municipio"]:
        municipios = st.multiselect("Município", sorted(resumo[cols["municipio"]].dropna().astype(str).unique()))
    df = filter_global(resumo, cols, municipios, regionais)

bases = {
    "Predição 7 dias": load_csv("predicao_calor_7d_municipal_v6.csv"),
    "Alerta inteligente": load_csv("alerta_inteligente_municipal_v6.csv"),
    "Priorização epidemiológica": load_csv("v9_priorizacao_epidemiologica.csv"),
    "Qualidade do ar": load_csv("qualidade_ar_municipal.csv"),
    "Ocupação hospitalar": load_csv("hospital_ocupacao_municipio.csv"),
    "Operacional CNES": load_csv("ops_resumo_operacional_cnes.csv"),
    "GeoCalor status": load_csv("geocalor_status_modelagem_v11_12.csv"),
    "GeoCalor RR municipal": load_csv("geocalor_cardioresp_rr_municipal_v11_12.csv"),
    "Status alertas VIGIA": load_csv("status_alertas_vigia.csv"),
}
geo_cuiaba, geo_cuiaba_src = load_geocalor_cuiaba()
bases["GeoCalor Cuiabá"] = geo_cuiaba

nivel_estadual = max(df["nivel_norm"], key=lambda x: ORDEM.get(x, 0)) if not df.empty else "cinza"
st.markdown(f"<div style='background:{CORES.get(nivel_estadual)};color:white;padding:14px 18px;border-radius:12px'><b>Nível operacional estadual: {nivel_estadual.upper()}</b></div>", unsafe_allow_html=True)

tabs = st.tabs([
    "1. Sumário Executivo", "2. Território e Mapas", "3. Município / Regional",
    "4. Pressão Assistencial", "5. Saúde", "6. Clima e Ar", "7. Vulnerabilidade",
    "8. Predição e Alertas", "9. GeoCalor", "10. Catálogo de Indicadores", "11. Administração Técnica"
])

with tabs[0]:
    dist = df["nivel_norm"].value_counts().reindex(["verde","amarela","laranja","vermelha","roxa","cinza"]).fillna(0).astype(int).reset_index()
    dist.columns = ["nivel", "municipios"]
    cols_m = st.columns(6)
    for i, row in dist.iterrows():
        cols_m[i].metric(str(row["nivel"]).capitalize(), int(row["municipios"]))
    st.plotly_chart(px.bar(dist, x="nivel", y="municipios", color="nivel", color_discrete_map=CORES, title="Distribuição municipal por cor de risco"), use_container_width=True)
    k = st.columns(6)
    k[0].metric("Municípios", len(df))
    k[1].metric("Tmax máx.", fmt(metric(df, ["tmax"]), " °C"))
    k[2].metric("UTCI máx.", fmt(metric(df, ["utci_proxy"])))
    k[3].metric("Risco 3d máx.", fmt(metric(df, ["risco_cumulativo_3d"]), digits=2))
    k[4].metric("Ocupação média", fmt(metric(df, ["ocupacao_leitos_pct", "taxa_ocupacao_pct"], "mean"), "%"))
    k[5].metric("PM2.5 máx.", fmt(metric(df, ["pm25_ugm3", "pm25", "pm2_5"])))
    map_layer(df, cols, "nivel_norm", "Mapa municipal por cor de risco", True)

with tabs[1]:
    layers = {
        "Nível operacional": ("nivel_norm", True), "Temperatura máxima": ("tmax", False),
        "UTCI/proxy": ("utci_proxy", False), "Risco cumulativo 3d": ("risco_cumulativo_3d", False),
        "Ocupação de leitos": ("ocupacao_leitos_pct", False), "Pressão assistencial/calor": ("pressao_calor_pct", False),
        "PM2.5": ("pm25_ugm3", False), "Vulnerabilidade": ("indice_vulnerabilidade_calor", False),
    }
    layer = st.selectbox("Camada", list(layers))
    col, discrete = layers[layer]
    if col in df.columns:
        map_layer(df, cols, col, f"Mapa — {layer}", discrete)
    else:
        pending("Camada não publicada", f"A coluna `{col}` não existe em data/public/resumo_municipal_atual.csv.")

with tabs[2]:
    st.subheader("Município / Regional")
    if not cols["municipio"]:
        pending("Município indisponível", "A base resumo_municipal_atual.csv não possui coluna municipal.")
    else:
        lista = sorted(df[cols["municipio"]].dropna().astype(str).unique())
        sel = st.selectbox("Município", lista, index=lista.index("Cuiabá") if "Cuiabá" in lista else 0)
        foco = df[df[cols["municipio"]].astype(str) == sel]
        cod_ibge = foco[cols["cod_ibge"]].iloc[0] if not foco.empty and cols["cod_ibge"] else None
        c = st.columns(4)
        c[0].metric("Município", sel)
        c[1].metric("Nível", foco["nivel_norm"].iloc[0].upper() if not foco.empty else "—")
        c[2].metric("Tmax", fmt(metric(foco, ["tmax"]), " °C"))
        c[3].metric("Ocupação", fmt(metric(foco, ["ocupacao_leitos_pct", "taxa_ocupacao_pct"], "mean"), "%"))
        st.dataframe(foco, use_container_width=True, hide_index=True)

        st.markdown("### Fontes complementares")
        for name, data in bases.items():
            with st.expander(name):
                sub, status = filter_for_municipio(data, sel, cod_ibge)
                st.caption(status)
                if sub.empty:
                    st.info("Fonte ainda não publicada ou vazia.")
                else:
                    st.dataframe(sub, use_container_width=True, hide_index=True)

with tabs[3]:
    st.subheader("Pressão Assistencial")
    data = bases["Ocupação hospitalar"] if not bases["Ocupação hospitalar"].empty else df
    st.dataframe(data, use_container_width=True, hide_index=True)

with tabs[4]:
    st.subheader("Saúde")
    st.dataframe(bases["Priorização epidemiológica"] if not bases["Priorização epidemiológica"].empty else df, use_container_width=True, hide_index=True)

with tabs[5]:
    st.subheader("Clima e Ar")
    data = bases["Qualidade do ar"] if not bases["Qualidade do ar"].empty else df
    st.dataframe(data, use_container_width=True, hide_index=True)

with tabs[6]:
    st.subheader("Vulnerabilidade")
    if "indice_vulnerabilidade_calor" in df.columns:
        map_layer(df, cols, "indice_vulnerabilidade_calor", "Mapa — Vulnerabilidade ao calor", False)
    st.dataframe(df, use_container_width=True, hide_index=True)

with tabs[7]:
    st.subheader("Predição e Alertas")
    for name in ["Predição 7 dias", "Alerta inteligente", "Status alertas VIGIA"]:
        st.markdown(f"### {name}")
        data = bases[name]
        if data.empty:
            st.info("Fonte ainda não publicada.")
        else:
            st.dataframe(data, use_container_width=True, hide_index=True)

with tabs[8]:
    st.subheader("GeoCalor")
    st.markdown("### GeoCalor Cuiabá")
    st.caption(f"Fonte: {geo_cuiaba_src}")
    if geo_cuiaba.empty:
        pending("GeoCalor Cuiabá ausente", "Não foi encontrada fonte específica nem fallback municipal para Cuiabá em data/public.")
    else:
        st.dataframe(geo_cuiaba, use_container_width=True, hide_index=True)

    st.markdown("### GeoCalor RR municipal")
    if bases["GeoCalor RR municipal"].empty:
        st.info("Fonte não publicada.")
    else:
        st.dataframe(bases["GeoCalor RR municipal"], use_container_width=True, hide_index=True)

    st.markdown("### Status modelagem")
    if bases["GeoCalor status"].empty:
        st.info("Fonte não publicada.")
    else:
        st.dataframe(bases["GeoCalor status"], use_container_width=True, hide_index=True)

with tabs[9]:
    st.subheader("Catálogo de Indicadores")
    st.dataframe(indicator_catalog({"Resumo municipal": df, **bases}), use_container_width=True, hide_index=True)

with tabs[10]:
    st.subheader("Administração Técnica")
    rows = []
    for p in sorted(PUBLIC.glob("*")):
        if p.is_file():
            rows.append({"arquivo": p.name, "tamanho_kb": round(p.stat().st_size/1024, 1)})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
