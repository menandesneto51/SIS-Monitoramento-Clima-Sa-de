# -*- coding: utf-8 -*-
"""Formatação null-safe e interpretação de indicadores."""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from sisclima.engines.boletim_el_nino.constants import HIDRO_LABEL, INDISPONIVEL, NAO_CALCULADO, SIGLAS

_FMT_INT_ZERO_OK = True  # zero observado é válido quando explicitamente contado


def _pt_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def fmt_num(v: Any, casas: int = 1, suf: str = "") -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return INDISPONIVEL
    try:
        x = float(v)
        if casas <= 0:
            n = int(round(x))
            sinal = "-" if n < 0 else ""
            return f"{sinal}{_pt_int(abs(n))}{suf}"
        s = f"{x:.{casas}f}"
        inteiro, frac = s.split(".")
        sinal = ""
        if inteiro.startswith("-"):
            sinal = "-"
            inteiro = inteiro[1:]
        return f"{sinal}{_pt_int(int(inteiro))},{frac}{suf}"
    except (TypeError, ValueError):
        return INDISPONIVEL


def fmt_int(v: Any, *, zero_ok: bool = True) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return INDISPONIVEL
    try:
        n = int(round(float(v)))
        if n == 0 and not zero_ok:
            return INDISPONIVEL
        return _pt_int(n)
    except (TypeError, ValueError):
        return INDISPONIVEL


def fmt_frac(num: Any, den: Any, *, pct: bool = True) -> str:
    if num is None or den is None:
        return INDISPONIVEL
    try:
        n, d = float(num), float(den)
        if d <= 0:
            return NAO_CALCULADO
        if pct:
            return f"{fmt_int(n)} de {fmt_int(d)} ({fmt_num(100.0 * n / d, 1, '%')})"
        return f"{fmt_int(n)}/{fmt_int(d)}"
    except (TypeError, ValueError):
        return INDISPONIVEL


def fmt_plural(n: Any, singular: str, plural: str | None = None) -> str:
    """Formata contagem com singular/plural correto (ex.: 1 município / 2 municípios)."""
    if n is None or (isinstance(n, float) and pd.isna(n)):
        return INDISPONIVEL
    try:
        k = int(round(float(n)))
    except (TypeError, ValueError):
        return INDISPONIVEL
    pl = plural or (singular + "s")
    return f"{_pt_int(k)} {singular if k == 1 else pl}"


def fmt_date_pt(v: Any, *, longo: bool = False) -> str:
    """Data pública: 20/08/2026 ou 20/08/2026 às 00h00."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return INDISPONIVEL
    s = str(v).strip()
    if not s or s in {"—", "-", "nan", "NaT"}:
        return INDISPONIVEL
    try:
        ts = pd.to_datetime(s, errors="coerce")
        if pd.isna(ts):
            return s
        if longo:
            meses = (
                "", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
                "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
            )
            return f"{ts.day} de {meses[int(ts.month)]} de {ts.year}"
        base = ts.strftime("%d/%m/%Y")
        # Se houver componente horário não nulo no original, exibir
        if "T" in s or " " in s or ":" in s:
            if ts.hour or ts.minute or ("00:00" in s) or re.search(r"\d{2}:\d{2}", s):
                return f"{base} às {ts.hour:02d}h{ts.minute:02d}"
        return base
    except (TypeError, ValueError, OverflowError):
        return s


def humanize_label(chave: str) -> str:
    k = str(chave or "").strip()
    if k in HIDRO_LABEL:
        return HIDRO_LABEL[k]
    return k.replace("_", " ")


def fmt_counts(d: dict[str, Any] | None, *, ordem: list[str] | None = None) -> str:
    if not d:
        return INDISPONIVEL
    if ordem:
        items = [(k, d.get(k, 0)) for k in ordem if k in d or True]
        # incluir zeros da ordem + extras
        seen = set()
        parts = []
        for k in ordem:
            seen.add(k)
            parts.append(f"{humanize_label(k)}: {fmt_int(d.get(k, 0))}")
        for k, v in sorted(d.items(), key=lambda kv: (-int(kv[1] or 0), str(kv[0]))):
            if k not in seen:
                parts.append(f"{humanize_label(k)}: {fmt_int(v)}")
        return "; ".join(parts)
    parts = [
        f"{humanize_label(k)}: {fmt_int(v)}"
        for k, v in sorted(d.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))
    ]
    return "; ".join(parts) if parts else INDISPONIVEL


def fmt_metric_box(
    titulo: str,
    observado: str,
    referencia: str = "",
    interpretacao: str = "",
) -> str:
    linhas = [f"> **Como interpretar — {titulo}**", f"> Observado: {observado}"]
    if referencia:
        linhas.append(f"> Referência: {referencia}")
    if interpretacao:
        linhas.append(f"> Interpretação: {interpretacao}")
    return "\n".join(linhas)


def expand_siglas(text: str) -> str:
    """Expande siglas na primeira ocorrência no texto; normaliza setas e classes."""
    out = str(text or "")
    out = out.replace("->", "→")
    out = re.sub(r"\bclasses?\s+vermelh[oa]/rox[oa]\b", "classes vermelha e roxa", out, flags=re.I)
    out = re.sub(r"\bem\s+vermelho/rox[oa]\b", "nas classes vermelha e roxa", out, flags=re.I)
    out = re.sub(r"\bvermelho/rox[oa]\b", "classes vermelha e roxa", out, flags=re.I)
    out = re.sub(r"\bvermelha/rox[oa]\b", "vermelha e roxa", out, flags=re.I)
    out = re.sub(r"\bmunicípio\(s\)", "municípios", out, flags=re.I)
    out = re.sub(r"\baviso\(s\)", "avisos", out, flags=re.I)
    out = re.sub(r"\balerta\(s\)", "alertas", out, flags=re.I)
    out = re.sub(r"\bregistro\(s\)", "registros", out, flags=re.I)
    seen: set[str] = set()
    for sigla, expansao in sorted(SIGLAS.items(), key=lambda x: -len(x[0])):
        if sigla in seen:
            continue
        # PM2,5 e similares: vírgula quebra \b no meio do token
        if re.search(r"[,.]", sigla):
            pattern = re.compile(rf"(?<![\w]){re.escape(sigla)}(?![\w])")
        else:
            pattern = re.compile(rf"\b{re.escape(sigla)}\b(?!-)")
        # Evita expansão duplicada quando o nome por extenso já aparece no texto
        core = expansao.split(" (")[0].strip()
        if core and core in out:
            seen.add(sigla)
            continue
        if expansao in out:
            seen.add(sigla)
            continue
        if pattern.search(out):
            out = pattern.sub(expansao, out, count=1)
            seen.add(sigla)
    return out


def md_table(headers: list[str], rows: list[list[str]], *, vazio: str = INDISPONIVEL) -> str:
    if not rows:
        return f"_{vazio}_"

    def _cell(v: Any) -> str:
        s = str(v if v is not None else "").replace("\n", " ").replace("|", "/").strip()
        return s

    line = "| " + " | ".join(_cell(h) for h in headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = "\n".join("| " + " | ".join(_cell(c) for c in r) + " |" for r in rows)
    return f"{line}\n{sep}\n{body}"


def coverage_status(n_obs: int, n_total: int) -> dict[str, Any]:
    if n_total <= 0:
        return {"status": "indisponivel", "texto": INDISPONIVEL, "n_obs": 0, "n_total": 0}
    if n_obs <= 0:
        return {
            "status": "sem_observacoes",
            "texto": "Fonte sem observações válidas na data de referência.",
            "n_obs": 0,
            "n_total": n_total,
        }
    return {"status": "ok", "texto": f"{n_obs} de {n_total} municípios", "n_obs": n_obs, "n_total": n_total}
