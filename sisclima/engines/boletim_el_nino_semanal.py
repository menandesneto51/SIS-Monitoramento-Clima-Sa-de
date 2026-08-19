# -*- coding: utf-8 -*-
"""Relatório semanal El Niño para a sala de situação CIEVS-MT.

Segue o sumário do Painel El Niño INMET/INPE (boletim mensal, cenário ASO) e
cruza com o nowcast municipal da semana no ARARAS — não gera forecast sazonal.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from sisclima.core.config import ROOT
from sisclima.core.logging_utils import get_logger
from sisclima.engines.stages import STAGE_ORDER

log = get_logger(__name__)

CENARIO_PATH = ROOT / "config" / "painel_el_nino.yaml"
OUT_DIR = ROOT / "docs" / "apresentacoes"

_MESES = (
    "",
    "jan",
    "fev",
    "mar",
    "abr",
    "mai",
    "jun",
    "jul",
    "ago",
    "set",
    "out",
    "nov",
    "dez",
)

_SNAP_MUN_COLS = [
    "municipio",
    "regional_saude",
    "nivel",
    "tmax",
    "umidade_media",
    "pm25_ugm3",
    "focos_queimadas_7d",
    "situacao_hidro",
]


def load_cenario_oficial(path: Path | None = None) -> dict[str, Any]:
    target = path or CENARIO_PATH
    try:
        if not target.exists():
            return {}
        data = yaml.safe_load(target.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001
        log.warning("Não foi possível ler o cenário El Niño: %s", exc)
        return {}


def semana_iso(hoje: date | None = None) -> dict[str, Any]:
    d = hoje or date.today()
    iso = d.isocalendar()
    inicio = d - timedelta(days=d.weekday())
    fim = inicio + timedelta(days=6)
    return {
        "ano": int(iso.year),
        "semana": int(iso.week),
        "rotulo": f"SE {iso.week:02d}/{iso.year}",
        "inicio": inicio.isoformat(),
        "fim": fim.isoformat(),
        "periodo_pt": f"{inicio.day:02d} {_MESES[inicio.month]} – {fim.day:02d} {_MESES[fim.month]} {iso.year}",
        "gerado_em": datetime.now().isoformat(timespec="minutes"),
    }


def _n_level(df: pd.DataFrame, *niveis: str) -> int:
    if df is None or df.empty or "nivel" not in df.columns:
        return 0
    s = df["nivel"].astype(str).str.lower().str.strip()
    return int(s.isin({n.lower() for n in niveis}).sum())


def _median(df: pd.DataFrame, col: str) -> float | None:
    if df is None or df.empty or col not in df.columns:
        return None
    s = pd.to_numeric(df[col], errors="coerce")
    if s.notna().any():
        return float(s.median())
    return None


def _mean(df: pd.DataFrame, col: str) -> float | None:
    if df is None or df.empty or col not in df.columns:
        return None
    s = pd.to_numeric(df[col], errors="coerce")
    if s.notna().any():
        return float(s.mean())
    return None


def _sum(df: pd.DataFrame, col: str) -> float | None:
    if df is None or df.empty or col not in df.columns:
        return None
    s = pd.to_numeric(df[col], errors="coerce")
    if s.notna().any():
        return float(s.fillna(0).sum())
    return None


def _count_ge(df: pd.DataFrame, col: str, limiar: float) -> int:
    if df is None or df.empty or col not in df.columns:
        return 0
    s = pd.to_numeric(df[col], errors="coerce")
    return int((s >= limiar).sum())


def _count_le(df: pd.DataFrame, col: str, limiar: float) -> int:
    if df is None or df.empty or col not in df.columns:
        return 0
    s = pd.to_numeric(df[col], errors="coerce")
    return int((s <= limiar).sum())


def _coverage(df: pd.DataFrame, col: str) -> int:
    if df is None or df.empty or col not in df.columns:
        return 0
    return int(df[col].notna().sum())


def _counts(df: pd.DataFrame, col: str) -> dict[str, int]:
    if df is None or df.empty or col not in df.columns:
        return {}
    s = df[col].astype(str).str.strip().replace({"": "—", "nan": "—", "None": "—"})
    return {str(k): int(v) for k, v in s.value_counts().to_dict().items()}


def _row_dict(row: pd.Series, cols: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for c in cols:
        if c not in row.index:
            continue
        val = row.get(c)
        out[c] = None if pd.isna(val) else val
    return out


def _extremo(df: pd.DataFrame, col: str, *, ascending: bool = False) -> dict[str, Any] | None:
    if df is None or df.empty or col not in df.columns:
        return None
    work = df.copy()
    work["_v"] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna(subset=["_v"])
    if work.empty:
        return None
    row = work.sort_values("_v", ascending=ascending).iloc[0]
    cols = [c for c in ["municipio", "regional_saude", col] if c in work.columns]
    return _row_dict(row, cols)


def snapshot_operacional(resumo: pd.DataFrame) -> dict[str, Any]:
    df = resumo if resumo is not None else pd.DataFrame()
    n = int(len(df))
    nivel_counts = _counts(df, "nivel") if not df.empty else {}
    top: list[dict[str, Any]] = []
    regionais: list[dict[str, Any]] = []
    if not df.empty:
        work = df.copy()
        rank = work["nivel"].astype(str).str.lower().map(STAGE_ORDER) if "nivel" in work.columns else 0
        work["_rk"] = pd.to_numeric(rank, errors="coerce").fillna(-1)
        if "indice_prioridade_global" in work.columns:
            work["_pri"] = pd.to_numeric(work["indice_prioridade_global"], errors="coerce")
            work = work.sort_values(["_rk", "_pri"], ascending=[False, False])
        else:
            work = work.sort_values("_rk", ascending=False)
        cols = [c for c in _SNAP_MUN_COLS if c in work.columns]
        for _, row in work.head(10).iterrows():
            top.append(_row_dict(row, cols))
        if "regional_saude" in work.columns:
            for nome, sub in work.groupby("regional_saude"):
                regionais.append(
                    {
                        "regional": str(nome or "—"),
                        "n": int(len(sub)),
                        "n_vermelha_roxa": _n_level(sub, "vermelha", "roxa"),
                        "n_laranja": _n_level(sub, "laranja"),
                        "tmax_mediana": _median(sub, "tmax"),
                        "umidade_mediana": _median(sub, "umidade_media"),
                        "pm25_mediana": _median(sub, "pm25_ugm3"),
                        "focos_7d": _sum(sub, "focos_queimadas_7d"),
                    }
                )
            regionais.sort(
                key=lambda r: (
                    int(r.get("n_vermelha_roxa") or 0),
                    float(r.get("tmax_mediana") or 0),
                ),
                reverse=True,
            )
    data_ref = None
    for col in ("data_referencia", "data"):
        if col in df.columns and df[col].notna().any():
            data_ref = str(df[col].dropna().astype(str).iloc[0])[:10]
            break
    n_onda = 0
    if "onda_calor_p95_2d" in df.columns:
        flag = pd.to_numeric(df["onda_calor_p95_2d"], errors="coerce").fillna(0)
        n_onda = int((flag > 0).sum())
    return {
        "n_municipios": n,
        "data_referencia": data_ref,
        "n_vermelha_roxa": _n_level(df, "vermelha", "roxa"),
        "n_laranja": _n_level(df, "laranja"),
        "n_amarela": _n_level(df, "amarela"),
        "niveis": {str(k).lower(): int(v) for k, v in nivel_counts.items()},
        "tmax_mediana": _median(df, "tmax"),
        "tmax_media": _mean(df, "tmax"),
        "tmin_mediana": _median(df, "tmin"),
        "umidade_mediana": _median(df, "umidade_media"),
        "n_umidade_30": _count_le(df, "umidade_media", 30),
        "precip_mediana": _median(df, "precipitacao_mm"),
        "n_sem_chuva": _count_le(df, "precipitacao_mm", 0),
        "utci_mediana": _median(df, "utci_proxy"),
        "n_onda_calor": n_onda,
        "pm25_mediana": _median(df, "pm25_ugm3"),
        "n_pm25_15": _count_ge(df, "pm25_ugm3", 15),
        "n_pm25_25": _count_ge(df, "pm25_ugm3", 25),
        "n_pm25_50": _count_ge(df, "pm25_ugm3", 50),
        "qualidade_ar": _counts(df, "qualidade_ar_nivel"),
        "focos_7d_total": _sum(df, "focos_queimadas_7d"),
        "focos_24h_total": _sum(df, "focos_queimadas_24h"),
        "n_com_focos_7d": _count_ge(df, "focos_queimadas_7d", 1),
        "cobertura_focos": _coverage(df, "focos_queimadas_7d"),
        "solo_mediana": _median(df, "indice_saturacao_solo"),
        "solo_classes": _counts(df, "classe_saturacao_solo"),
        "hidro": _counts(df, "situacao_hidro"),
        "cobertura_hidro": _coverage(df, "situacao_hidro"),
        "prioritarios": top,
        "regionais": regionais,
        "extremos": {
            "tmax": _extremo(df, "tmax"),
            "pm25": _extremo(df, "pm25_ugm3"),
            "focos": _extremo(df, "focos_queimadas_7d"),
        },
    }


def _fmt_num(v, casas: int = 1, suf: str = "") -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    try:
        return f"{float(v):.{casas}f}{suf}"
    except (TypeError, ValueError):
        return "—"


def _fmt_int(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    try:
        return f"{int(round(float(v)))}"
    except (TypeError, ValueError):
        return "—"


def _fmt_counts(d: dict[str, Any] | None) -> str:
    if not d:
        return "—"
    parts = [f"{k} {v}" for k, v in sorted(d.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))]
    return "; ".join(parts)


def _fmt_ext(ext: dict[str, Any] | None, col: str, suf: str = "", *, inteiro: bool = False) -> str:
    if not ext:
        return "—"
    mun = ext.get("municipio") or "—"
    val = _fmt_int(ext.get(col)) if inteiro else _fmt_num(ext.get(col), 1, suf)
    if inteiro and suf:
        val = f"{val}{suf}"
    return f"{mun} ({val})"


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_Sem recorte nesta rodada._"
    line = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = "\n".join("| " + " | ".join(r) + " |" for r in rows)
    return f"{line}\n{sep}\n{body}"


def _narrativa(cenario: dict[str, Any], chave: str, fallback: str = "") -> str:
    bloco = cenario.get("narrativa") or {}
    txt = str(bloco.get(chave) or "").strip()
    return txt or fallback


def _frase_oficial(txt: str, fallback: str = "") -> str:
    s = str(txt or fallback or "").strip()
    return s[:-1] if s.endswith(".") else s


def leitura_cruzada(cenario: dict[str, Any], snap: dict[str, Any]) -> list[str]:
    mt = cenario.get("mato_grosso") or {}
    linhas = [
        (
            f"O ASO oficial aponta **temperatura acima da média** na Amazônia Legal; "
            f"nesta rodada a Tmáx mediana do ARARAS é **{_fmt_num(snap.get('tmax_mediana'), 1, ' °C')}** "
            f"({_fmt_int(snap.get('n_municipios'))} municípios; referência {snap.get('data_referencia') or '—'})."
        ),
        (
            f"A previsão aponta **baixa umidade** e maior potencial de queimadas; "
            f"a umidade relativa mediana é **{_fmt_num(snap.get('umidade_mediana'), 0, '%')}** "
            f"({_fmt_int(snap.get('n_umidade_30'))} municípios ≤ 30%) e "
            f"**{_fmt_int(snap.get('n_sem_chuva'))}** municípios sem chuva no dia de referência."
        ),
        (
            f"O boletim destaca **alerta alto de fogo em Mato Grosso**; o ARARAS observa "
            f"**{_fmt_int(snap.get('focos_7d_total'))}** focos em 7 dias "
            f"({_fmt_int(snap.get('n_com_focos_7d'))}/{_fmt_int(snap.get('cobertura_focos'))} municípios com foco) "
            f"e PM2,5 mediana **{_fmt_num(snap.get('pm25_mediana'), 1, ' µg/m³')}** "
            f"({_fmt_int(snap.get('n_pm25_25'))} municípios ≥ 25 µg/m³)."
        ),
        (
            f"Monitor de Secas (jun/2026): {_frase_oficial(mt.get('monitor_secas_jun2026'), 'MT livre de seca')}. "
            f"Hidrologia municipal no ARARAS cobre **{_fmt_int(snap.get('cobertura_hidro'))}** municípios "
            f"({_fmt_counts(snap.get('hidro'))}); saturação do solo mediana "
            f"**{_fmt_num(snap.get('solo_mediana'), 0)}**."
        ),
        (
            f"Bacia do Paraguai (oficial): {_frase_oficial(mt.get('hidro_pantanal'), 'seca severa a extrema')}. "
            f"Esse dado hidrológico de bacia **não é substituído** pelo nowcast de 7 dias."
        ),
    ]
    return linhas


def format_markdown(cenario: dict[str, Any], semana: dict[str, Any], snap: dict[str, Any], *, publico: bool = False) -> str:
    enso = cenario.get("enso") or {}
    mt = cenario.get("mato_grosso") or {}
    br = cenario.get("brasil_aso") or {}
    ext = snap.get("extremos") or {}
    recs = cenario.get("recomendacoes_estados") or []

    linhas_top = []
    for p in snap.get("prioritarios") or []:
        mun = p.get("municipio") or "—"
        reg = p.get("regional_saude") or "—"
        niv = str(p.get("nivel") or "—").upper()
        tmax = _fmt_num(p.get("tmax"), 1, " °C")
        umi = _fmt_num(p.get("umidade_media"), 0, "%")
        pm = _fmt_num(p.get("pm25_ugm3"), 1, " µg/m³")
        focos = _fmt_int(p.get("focos_queimadas_7d"))
        linhas_top.append([mun, reg, niv, tmax, umi, pm, focos])
    tab_prior = _md_table(
        ["Município", "Regional", "Nível", "Tmáx", "UR", "PM2,5", "Focos 7d"],
        linhas_top,
    )

    linhas_reg = []
    for r in (snap.get("regionais") or [])[:12]:
        linhas_reg.append(
            [
                str(r.get("regional") or "—"),
                _fmt_int(r.get("n")),
                _fmt_int(r.get("n_vermelha_roxa")),
                _fmt_int(r.get("n_laranja")),
                _fmt_num(r.get("tmax_mediana"), 1, " °C"),
                _fmt_num(r.get("umidade_mediana"), 0, "%"),
                _fmt_num(r.get("pm25_mediana"), 1),
                _fmt_int(r.get("focos_7d")),
            ]
        )
    tab_reg = _md_table(
        ["Regional", "Mun.", "Verm./roxa", "Laranja", "Tmáx med.", "UR med.", "PM2,5", "Focos 7d"],
        linhas_reg,
    )

    cruz = "\n".join(f"- {x}" for x in leitura_cruzada(cenario, snap))
    rec_md = "\n".join(f"- {x}" for x in recs) if recs else "- Sem recomendações cadastradas no YAML oficial."

    pauta = ""
    if not publico:
        pauta = """
## 9. Pauta sugerida da sala

1. Conferir se calor, fumaça e hidro da semana estão coerentes com o ASO oficial (seções 3–5).
2. Checar regionais com vermelha/roxa e PM2,5 ≥ 25 (máscara / farmácia / comunicação de risco).
3. Manter Monitor de Secas e bacia do Paraguai como leitura hidrológica — não só o nowcast de 7 dias.
4. Decisão humana: o ARARAS não ativa COE; documentar se há mudança de postura.
"""

    titulo = (
        "Relatório semanal El Niño — ARARAS MT"
        if publico
        else "Relatório semanal El Niño — sala de situação CIEVS-MT"
    )
    secao_mun = "Municípios em destaque" if publico else "Municípios prioritários para o plantão"

    return f"""# {titulo}

**{semana.get('rotulo')}** ({semana.get('periodo_pt')})  
Padrão: Painel El Niño 2026-2027, boletim mensal n.º {cenario.get('edicao', '—')} ({cenario.get('mes_referencia', '—')}) · trimestre {cenario.get('trimestre', '—')}.  
Órgãos do cenário oficial: {cenario.get('orgaos', 'INMET, INPE, ANA, CEMADEN, SGB, SEDEC, CENSIPAM')}.  
Dados da semana: ARARAS MT · `resumo_municipal_atual` · referência **{snap.get('data_referencia') or 'rodada atual'}** · gerado em {semana.get('gerado_em')}.

> A predição operacional de ~7 dias **não substitui** o cenário trimestral. Números municipais **não** saem do PDF federal — saem do ARARAS.

## 1. Análise da situação atual do El Niño

{_narrativa(cenario, 'situacao_atual', str(enso.get('status') or '—'))}

- **ENSO:** {enso.get('status', '—')}
- **Niño 3.4 (boletim):** {enso.get('nino34_recente', '—')}
- **Intensidade:** {enso.get('intensidade', '—')}

## 2. Perspectivas do El Niño

{_narrativa(cenario, 'perspectivas', str(enso.get('persistencia') or '—'))}

- **Persistência:** {enso.get('persistencia', '—')}

## 3. Previsão climática sazonal (ASO/2026)

{_narrativa(cenario, 'previsao_aso', str(br.get('chuva') or '—'))}

- **Chuva (Brasil):** {br.get('chuva', '—')}
- **Temperatura (Brasil):** {br.get('temperatura', '—')}

### Amazônia Legal e Mato Grosso

{_narrativa(cenario, 'amazonia_legal', str(mt.get('chuva') or '—'))}

- **Chuva em MT:** {mt.get('chuva', '—')}
- **Temperatura em MT:** {mt.get('temperatura', '—')}

## 4. Panorama dos recursos hídricos (recorte MT)

{_narrativa(cenario, 'centro_oeste_monitor', str(mt.get('monitor_secas_jun2026') or '—'))}

{_narrativa(cenario, 'hidro_paraguai', str(mt.get('hidro_pantanal') or '—'))}

### Observado nesta semana (ARARAS — dados reais)

- Saturação do solo mediana: **{_fmt_num(snap.get('solo_mediana'), 0)}** · classes: {_fmt_counts(snap.get('solo_classes'))}
- Situação hidro municipal: {_fmt_counts(snap.get('hidro'))} (cobertura **{_fmt_int(snap.get('cobertura_hidro'))}/{_fmt_int(snap.get('n_municipios'))}**)
- Precipitação mediana no dia de referência: **{_fmt_num(snap.get('precip_mediana'), 1, ' mm')}** · municípios sem chuva: **{_fmt_int(snap.get('n_sem_chuva'))}**

## 5. Risco de fogo e qualidade do ar

{_narrativa(cenario, 'risco_fogo', str(mt.get('risco_fogo') or '—'))}

### Observado nesta semana (ARARAS — dados reais)

- Focos 7 dias: **{_fmt_int(snap.get('focos_7d_total'))}** · 24 h: **{_fmt_int(snap.get('focos_24h_total'))}** · municípios com foco: **{_fmt_int(snap.get('n_com_focos_7d'))}**
- Extremo de focos 7d: {_fmt_ext(ext.get('focos'), 'focos_queimadas_7d', inteiro=True)}
- PM2,5 mediana: **{_fmt_num(snap.get('pm25_mediana'), 1, ' µg/m³')}** · ≥15: {_fmt_int(snap.get('n_pm25_15'))} · ≥25: {_fmt_int(snap.get('n_pm25_25'))} · ≥50: {_fmt_int(snap.get('n_pm25_50'))}
- Extremo de PM2,5: {_fmt_ext(ext.get('pm25'), 'pm25_ugm3', ' µg/m³')}
- IQA (níveis): {_fmt_counts(snap.get('qualidade_ar'))}

## 6. Semana operacional no ARARAS MT (dados reais)

- Municípios no recorte: **{_fmt_int(snap.get('n_municipios'))}**
- Níveis: vermelha/roxa **{_fmt_int(snap.get('n_vermelha_roxa'))}** · laranja **{_fmt_int(snap.get('n_laranja'))}** · amarela **{_fmt_int(snap.get('n_amarela'))}** · detalhe {_fmt_counts(snap.get('niveis'))}
- Tmáx mediana / média: **{_fmt_num(snap.get('tmax_mediana'), 1, ' °C')}** / {_fmt_num(snap.get('tmax_media'), 1, ' °C')} · Tmín mediana: {_fmt_num(snap.get('tmin_mediana'), 1, ' °C')}
- Extremo de Tmáx: {_fmt_ext(ext.get('tmax'), 'tmax', ' °C')}
- UTCI proxy mediana: **{_fmt_num(snap.get('utci_mediana'), 1, ' °C')}** · municípios em onda de calor (P95 2d): **{_fmt_int(snap.get('n_onda_calor'))}**

### Regionais de saúde

{tab_reg}

### {secao_mun}

{tab_prior}

## 7. Leitura cruzada (cenário ASO × semana ARARAS)

{cruz}

## 8. Recomendações oficiais aos estados e municípios

Fonte: seção 6 do Painel El Niño n.º {cenario.get('edicao', '—')} (não são gatilhos automáticos do ARARAS).

{rec_md}
{pauta}
---
Referências: INMET et al., *Painel El Niño 2026-2027*, boletim n.º {cenario.get('edicao', '—')}, jul. 2026. CIEVS-MT, ARARAS MT (`resumo_municipal_atual`). `docs/apresentacoes/REFERENCIAS_ABNT_6023.md`.
"""


def build_boletim_semanal(resumo: pd.DataFrame, *, hoje: date | None = None, publico: bool = False) -> dict[str, Any]:
    cenario = load_cenario_oficial()
    semana = semana_iso(hoje)
    snap = snapshot_operacional(resumo)
    md = format_markdown(cenario, semana, snap, publico=publico)
    return {
        "semana": semana,
        "cenario": cenario,
        "snapshot": snap,
        "markdown": md,
        "arquivo": f"Boletim_ElNino_{semana['rotulo'].replace(' ', '_').replace('/', '-')}.md",
    }


def save_boletim(payload: dict[str, Any], out_dir: Path | None = None) -> Path:
    dest_dir = out_dir or OUT_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / str(payload.get("arquivo") or "Boletim_ElNino_semanal.md")
    path.write_text(str(payload.get("markdown") or ""), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Relatório semanal El Niño — sala de situação")
    p.add_argument("--out-dir", default=None, help="Pasta de saída (padrão docs/apresentacoes)")
    p.add_argument("--publico", action="store_true", help="Omite pauta interna da sala")
    args = p.parse_args(argv)
    from sisclima.core.db import read_table

    resumo = read_table("resumo_municipal_atual")
    payload = build_boletim_semanal(resumo, publico=bool(args.publico))
    out = Path(args.out_dir) if args.out_dir else None
    path = save_boletim(payload, out)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
