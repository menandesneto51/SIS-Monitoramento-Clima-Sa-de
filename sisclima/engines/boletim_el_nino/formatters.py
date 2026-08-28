# -*- coding: utf-8 -*-
"""Formatação null-safe e interpretação de indicadores."""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from sisclima.engines.boletim_el_nino.constants import HIDRO_LABEL, INDISPONIVEL, NAO_CALCULADO, NIVEIS_CLASSE_ORDEM, SIGLAS

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


def plural_pt(n: Any, singular: str, plural: str | None = None) -> str:
    """Retorna só a forma verbal: plural_pt(1, 'aviso', 'avisos') → 'aviso'."""
    if n is None or (isinstance(n, float) and pd.isna(n)):
        return plural or (singular + "s")
    try:
        k = int(round(float(n)))
    except (TypeError, ValueError):
        return plural or (singular + "s")
    pl = plural or (singular + "s")
    return singular if k == 1 else pl


pluralize_pt = plural_pt  # alias QA de publicação


def fmt_plural(n: Any, singular: str, plural: str | None = None) -> str:
    """Formata contagem com singular/plural correto (ex.: 1 município / 2 municípios)."""
    if n is None or (isinstance(n, float) and pd.isna(n)):
        return INDISPONIVEL
    try:
        k = int(round(float(n)))
    except (TypeError, ValueError):
        return INDISPONIVEL
    return f"{_pt_int(k)} {plural_pt(k, singular, plural)}"


def _fix_singular_plural(text: str) -> str:
    """Corrige '1 avisos', '1 municípios' e formas com (s)."""
    out = str(text or "")
    pares = (
        ("aviso", "avisos"),
        ("município", "municípios"),
        ("comunidade", "comunidades"),
        ("aldeia", "aldeias"),
        ("registro", "registros"),
        ("nível", "níveis"),
        ("nivel", "niveis"),
        ("caso", "casos"),
        ("foco", "focos"),
        ("alerta", "alertas"),
    )
    for sing, plur in pares:
        out = re.sub(
            rf"(?<![0-9.,])1\s+{re.escape(plur)}\b",
            f"1 {sing}",
            out,
            flags=re.I,
        )
        out = re.sub(
            rf"(?<![0-9.,])1\s+{re.escape(sing)}\(s\)",
            f"1 {sing}",
            out,
            flags=re.I,
        )
        out = re.sub(
            rf"(?<![0-9.,])(\d{{2,}}|[2-9])\s+{re.escape(sing)}\(s\)",
            rf"\1 {plur}",
            out,
            flags=re.I,
        )
        out = re.sub(
            rf"\b{re.escape(sing)}\(s\)",
            plur,
            out,
            flags=re.I,
        )
    return out


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


def fmt_distribuicao_niveis(d: dict[str, Any] | None) -> str:
    """Sempre lista as cinco classes, inclusive quando o valor é zero."""
    d = d or {}
    return "; ".join(f"{k} {fmt_int(d.get(k, 0))}" for k in NIVEIS_CLASSE_ORDEM)


def fmt_pareamento(sem: Any, n_tot: Any) -> str:
    """1 de 142 municípios (0,7%). — sem aninhar '1 município (1 de 142 …)'."""
    if not sem:
        return ""
    try:
        n, d = float(sem), float(n_tot)
        if d <= 0:
            return ""
        return f"{fmt_int(n)} de {fmt_int(d)} municípios ({fmt_num(100.0 * n / d, 1, '%')})."
    except (TypeError, ValueError):
        return ""


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
    out = out.replace("->", "→").replace("^", "↑")
    out = re.sub(r"(?<![A-Za-zÀ-ÿ])v(?=\s*\d)", "↓", out)
    out = re.sub(r"sinal hidrológico de alerta", "sinal hidrológico de baixa disponibilidade", out, flags=re.I)
    out = re.sub(r"não tratar a classes", "não interpretar as classes", out, flags=re.I)
    out = re.sub(r"\bclasses?\s+vermelh[oa]/rox[oa]\b", "classes vermelha e roxa", out, flags=re.I)
    out = re.sub(r"\bem\s+vermelho/rox[oa]\b", "nas classes vermelha e roxa", out, flags=re.I)
    out = re.sub(r"\bvermelho/rox[oa]\b", "classes vermelha e roxa", out, flags=re.I)
    out = re.sub(r"\bvermelha/rox[oa]\b", "vermelha e roxa", out, flags=re.I)
    out = _fix_singular_plural(out)
    seen: set[str] = set()
    if re.search(
        r"Sala de Situação do Centro de Informações Estratégicas em "
        r"Vigilância em Saúde de Mato Grosso \(CIEVS-MT\)",
        out,
    ):
        seen.add("CIEVS-MT")
    for sigla, expansao in sorted(SIGLAS.items(), key=lambda x: -len(x[0])):
        if sigla in seen:
            continue
        if re.search(r"[,.]", sigla):
            pattern = re.compile(rf"(?<![\w]){re.escape(sigla)}(?![\w])")
        else:
            pattern = re.compile(rf"\b{re.escape(sigla)}\b(?!-)")
        m = pattern.search(out)
        if not m:
            continue
        prefix = out[: m.start()]
        core = expansao.split(" (")[0].strip()
        core_plain = re.sub(r"[*_]", "", core)
        if expansao in prefix or (core and core in prefix) or (core_plain and core_plain in prefix):
            seen.add(sigla)
            continue
        out = pattern.sub(expansao, out, count=1)
        seen.add(sigla)
    return _fix_singular_plural(out)


def bloco_tabela(titulo: str, corpo: str, fonte: str, nota: str | None = None) -> str:
    """Identificação acima + tabela + fonte abaixo (NBR 14724). Numeração sequencial no fechamento."""
    parts = [f"**Tabela – {titulo}**", "", corpo, "", f"Fonte: {fonte}"]
    if nota:
        parts.extend(["", f"Nota: {nota}"])
    return "\n".join(parts)


def numerar_tabelas(text: str) -> str:
    """Atribui Tabela 1, 2, 3… na ordem de aparição. Não reinicia."""
    n = 0

    def _repl(m: re.Match) -> str:
        nonlocal n
        n += 1
        return f"**Tabela {n} – {m.group(1).strip()}**"

    return re.sub(r"\*\*Tabela(?:\s+\d+)?\s*[–-]\s*([^*]+)\*\*", _repl, str(text or ""))


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
