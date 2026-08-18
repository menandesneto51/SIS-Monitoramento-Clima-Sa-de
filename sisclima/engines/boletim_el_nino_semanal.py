# -*- coding: utf-8 -*-
"""Boletim semanal El Niño para a sala de situação CIEVS-MT.

O Painel El Niño INMET/INPE é mensal (cenário ASO). Este produto cruza esse
cenário oficial com o nowcast municipal da semana — não gera forecast sazonal.
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


def _count_ge(df: pd.DataFrame, col: str, limiar: float) -> int:
    if df is None or df.empty or col not in df.columns:
        return 0
    s = pd.to_numeric(df[col], errors="coerce")
    return int((s >= limiar).sum())


def snapshot_operacional(resumo: pd.DataFrame) -> dict[str, Any]:
    df = resumo if resumo is not None else pd.DataFrame()
    n = int(len(df))
    nivel_counts = {}
    if not df.empty and "nivel" in df.columns:
        nivel_counts = df["nivel"].astype(str).str.lower().str.strip().value_counts().to_dict()
    top: list[dict[str, Any]] = []
    if not df.empty:
        work = df.copy()
        rank = work["nivel"].astype(str).str.lower().map(STAGE_ORDER) if "nivel" in work.columns else 0
        work["_rk"] = pd.to_numeric(rank, errors="coerce").fillna(-1)
        if "indice_prioridade_global" in work.columns:
            work["_pri"] = pd.to_numeric(work["indice_prioridade_global"], errors="coerce")
            work = work.sort_values(["_rk", "_pri"], ascending=[False, False])
        else:
            work = work.sort_values("_rk", ascending=False)
        cols = [c for c in ["municipio", "regional_saude", "nivel", "tmax", "pm25_ugm3"] if c in work.columns]
        for _, row in work.head(8).iterrows():
            top.append({c: (None if pd.isna(row.get(c)) else row.get(c)) for c in cols})
    return {
        "n_municipios": n,
        "n_vermelha_roxa": _n_level(df, "vermelha", "roxa"),
        "n_laranja": _n_level(df, "laranja"),
        "n_amarela": _n_level(df, "amarela"),
        "niveis": {str(k): int(v) for k, v in nivel_counts.items()},
        "tmax_mediana": _median(df, "tmax"),
        "pm25_mediana": _median(df, "pm25_ugm3"),
        "n_pm25_25": _count_ge(df, "pm25_ugm3", 25),
        "n_pm25_50": _count_ge(df, "pm25_ugm3", 50),
        "prioritarios": top,
    }


def _fmt_num(v, casas: int = 1, suf: str = "") -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    try:
        return f"{float(v):.{casas}f}{suf}"
    except (TypeError, ValueError):
        return "—"


def format_markdown(cenario: dict[str, Any], semana: dict[str, Any], snap: dict[str, Any]) -> str:
    enso = cenario.get("enso") or {}
    mt = cenario.get("mato_grosso") or {}
    linhas_top = []
    for p in snap.get("prioritarios") or []:
        mun = p.get("municipio") or "—"
        niv = str(p.get("nivel") or "—").upper()
        tmax = _fmt_num(p.get("tmax"), 1, " °C")
        pm = _fmt_num(p.get("pm25_ugm3"), 1, " µg/m³")
        linhas_top.append(f"- **{mun}** · {niv} · Tmáx {tmax} · PM2,5 {pm}")
    if not linhas_top:
        linhas_top = ["- Sem ranking municipal nesta rodada."]
    return f"""# Boletim semanal El Niño — sala de situação CIEVS-MT

**{semana.get('rotulo')}** ({semana.get('periodo_pt')})  
Gerado em {semana.get('gerado_em')} · ARARAS MT

## 1. Cenário oficial (não é output do ARARAS)

Fonte: {cenario.get('titulo', 'Painel El Niño')} · boletim n.º {cenario.get('edicao', '—')} ({cenario.get('mes_referencia', '—')}) · trimestre {cenario.get('trimestre', '—')}.  
Órgãos: {cenario.get('orgaos', 'INMET/INPE/ANA/CEMADEN')}.

- **ENSO:** {enso.get('status', '—')}
- **Intensidade:** {enso.get('intensidade', '—')}
- **Persistência:** {enso.get('persistencia', '—')}
- **Chuva MT (ASO):** {mt.get('chuva', '—')}
- **Temperatura:** {mt.get('temperatura', '—')}
- **Risco de fogo:** {mt.get('risco_fogo', '—')}
- **Hidro Pantanal:** {mt.get('hidro_pantanal', '—')}

A predição operacional de ~7 dias **não substitui** este cenário trimestral.

## 2. Semana operacional (ARARAS)

- Municípios no recorte: **{snap.get('n_municipios', 0)}**
- Vermelha/roxa: **{snap.get('n_vermelha_roxa', 0)}** · Laranja: **{snap.get('n_laranja', 0)}** · Amarela: **{snap.get('n_amarela', 0)}**
- Tmáx mediana: **{_fmt_num(snap.get('tmax_mediana'), 1, ' °C')}**
- PM2,5 mediana: **{_fmt_num(snap.get('pm25_mediana'), 1, ' µg/m³')}**
- Municípios com PM2,5 ≥ 25: **{snap.get('n_pm25_25', 0)}** · ≥ 50: **{snap.get('n_pm25_50', 0)}**

## 3. Prioritários para o plantão

{chr(10).join(linhas_top)}

## 4. Pauta sugerida da sala

1. Confirmar se o sinal da semana (calor, fumaça, hidro) está coerente com o ASO oficial.
2. Checar regionais com vermelha/roxa e PM2,5 ≥ 25 (máscara / farmácia).
3. Manter Monitor de Secas e bacia do Paraguai como leitura hidrológica — não só o nowcast de 7 dias.
4. Decisão humana: o ARARAS não ativa COE; documentar se há mudança de postura.

Referência: `docs/apresentacoes/REFERENCIAS_ABNT_6023.md`.
"""


def build_boletim_semanal(resumo: pd.DataFrame, *, hoje: date | None = None) -> dict[str, Any]:
    cenario = load_cenario_oficial()
    semana = semana_iso(hoje)
    snap = snapshot_operacional(resumo)
    md = format_markdown(cenario, semana, snap)
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
    p = argparse.ArgumentParser(description="Boletim semanal El Niño — sala de situação")
    p.add_argument("--out-dir", default=None, help="Pasta de saída (padrão docs/apresentacoes)")
    args = p.parse_args(argv)
    from sisclima.core.db import read_table

    resumo = read_table("resumo_municipal_atual")
    payload = build_boletim_semanal(resumo)
    out = Path(args.out_dir) if args.out_dir else None
    path = save_boletim(payload, out)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
