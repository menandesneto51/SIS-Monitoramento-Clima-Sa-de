# -*- coding: utf-8 -*-
"""Busca IOMAT + imprensa por decretos/emergências correlatos ao ARARAS MT."""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import Any
from urllib.parse import quote_plus, urlencode

import pandas as pd
import yaml

from sisclima.core.config import ROOT
from sisclima.core.db import write_df
from sisclima.core.http_client import http_get
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

_CFG_PATH = ROOT / "config" / "iomat_decretos_emergencia.yaml"
_TABLE_DEFAULT = "iomat_decretos_emergencia"

_RE_DECRETO = re.compile(
    r"(DECRETO|PORTARIA|RESOLU[CÇ][AÃ]O)\s*(N[º°o\.]*\s*)?([\d\.]+/?[\d]*)",
    re.I,
)
_RE_MUNICIPIO = re.compile(
    r"(?:Munic[ií]pio(?:s)?\s+de\s+|nos?\s+Munic[ií]pios?\s+de\s+)([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç\s,\-]{2,80})",
    re.I,
)


def load_config() -> dict[str, Any]:
    if not _CFG_PATH.exists():
        return {}
    return yaml.safe_load(_CFG_PATH.read_text(encoding="utf-8")) or {}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _score_relevancia(texto: str, cfg: dict[str, Any]) -> tuple[float, list[str]]:
    t = texto.casefold()
    rel = cfg.get("relevancia") or {}
    temas = [str(x) for x in (rel.get("temas_araras") or [])]
    exige = [str(x) for x in (rel.get("exige_ao_menos_um") or [])]
    excluir = [str(x) for x in (rel.get("excluir_se_somente") or [])]

    hits_tema = [k for k in temas if k.casefold() in t]
    hits_exige = [k for k in exige if k.casefold() in t]
    if not hits_exige and not hits_tema:
        return 0.0, []
    # ruído: só termos de exclusão e nenhum tema ARARAS
    if hits_tema == [] and any(k.casefold() in t for k in excluir):
        return 0.0, []

    score = 10.0 * len(hits_exige) + 15.0 * len(hits_tema)
    if "situação de emergência" in t or "estado de calamidade" in t:
        score += 25.0
    if "decreto" in t:
        score += 5.0
    return float(min(100.0, score)), sorted(set(hits_tema + hits_exige))


def _extrair_titulo(conteudo: str) -> str:
    text = _norm(conteudo or "")
    # Preferir ato no início do trecho (menos ruído de páginas longas)
    for m in _RE_DECRETO.finditer(text):
        start = m.start()
        # janela a partir do match até pontuação forte ou 200 chars
        trecho = text[start : start + 220]
        trecho = re.split(r"(?<=\.)\s+(?:O\s+GOVERNADOR|Art\.|CONSIDERANDO|RESOLVE)", trecho, maxsplit=1)[0]
        trecho = _norm(trecho)
        if len(trecho) >= 20:
            return trecho[:180]
    return text[:140]


def _extrair_municipios(conteudo: str) -> str:
    m = _RE_MUNICIPIO.search(conteudo or "")
    if not m:
        return ""
    raw = _norm(m.group(1))
    # corta em verbos típicos
    raw = re.split(r"\s+(?:em\s+decorrência|com\s+|conforme|e\s+dá|no\s+Estado)", raw, maxsplit=1)[0]
    return raw[:120]


def _uid(*parts: Any) -> str:
    base = "|".join(str(p or "") for p in parts)
    return hashlib.sha1(base.encode("utf-8", errors="ignore")).hexdigest()[:16]


def buscar_iomat(
    *,
    consultas: list[str] | None = None,
    pages: int | None = None,
    cfg: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Consulta a API pública de busca do IOMAT (JSON Elasticsearch-like)."""
    cfg = cfg or load_config()
    iomat = cfg.get("iomat") or {}
    base = str(iomat.get("base_url") or "https://www.iomat.mt.gov.br").rstrip("/")
    path_tpl = str(iomat.get("search_path") or "/busca/busca/buscar/query/{page}/")
    n_pages = int(pages if pages is not None else iomat.get("pages_por_termo") or 2)
    timeout = int(iomat.get("timeout_seconds") or 45)
    ua = str(iomat.get("user_agent") or "ARARAS-MT/1.0")
    termos = consultas or list(cfg.get("consultas_iomat") or ["situação de emergência"])

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for termo in termos:
        termo = _norm(termo)
        if len(termo) < int(iomat.get("min_query_chars") or 3):
            continue
        for page in range(1, n_pages + 1):
            path = path_tpl.format(page=page)
            url = f"{base}{path}?1=1&q={quote_plus(termo)}"
            try:
                r = http_get(url, timeout=timeout, headers={"User-Agent": ua, "Accept": "application/json"})
                r.raise_for_status()
                payload = r.json()
            except Exception as exc:  # noqa: BLE001
                log.warning("IOMAT busca falhou (%s p%d): %s", termo, page, exc)
                break

            hits = ((payload or {}).get("hits") or {}).get("hits") or []
            if not hits:
                break
            for h in hits:
                src = h.get("_source") or {}
                conteudo = str(src.get("conteudo") or "")
                data = str(src.get("data") or "")
                pagina = src.get("pagina")
                diario_id = src.get("diario_id")
                pdf_id = src.get("pdf_id")
                uid = _uid(diario_id, pagina, pdf_id, data, conteudo[:80])
                if uid in seen:
                    continue
                seen.add(uid)
                score, tags = _score_relevancia(conteudo, cfg)
                if score <= 0:
                    continue
                link_pdf = f"{base}/portal/edicoes/download/{diario_id}" if diario_id else ""
                rows.append(
                    {
                        "uid": uid,
                        "fonte": "IOMAT",
                        "consulta": termo,
                        "data_publicacao": data,
                        "titulo": _extrair_titulo(conteudo),
                        "municipios_mencionados": _extrair_municipios(conteudo),
                        "pagina": pagina,
                        "diario_id": diario_id,
                        "pdf_id": pdf_id,
                        "url": link_pdf,
                        "score_relevancia": score,
                        "tags": "; ".join(tags),
                        "trecho": _norm(conteudo)[:500],
                        "coletado_em": datetime.now().isoformat(timespec="seconds"),
                    }
                )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df.sort_values(["score_relevancia", "data_publicacao"], ascending=[False, False])
    return df.reset_index(drop=True)


def buscar_imprensa(*, cfg: dict[str, Any] | None = None) -> pd.DataFrame:
    """Sinais de imprensa via Google News RSS (auxiliar — validar no IOMAT)."""
    cfg = cfg or load_config()
    imp = cfg.get("imprensa") or {}
    if not imp.get("habilitado", True):
        return pd.DataFrame()

    base_rss = str(imp.get("google_news_rss") or "https://news.google.com/rss/search")
    consultas = list(imp.get("consultas") or [])
    max_n = int(imp.get("max_itens_por_consulta") or 15)
    timeout = int(imp.get("timeout_seconds") or 30)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for termo in consultas:
        params = {"q": termo, "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"}
        url = f"{base_rss}?{urlencode(params)}"
        try:
            r = http_get(url, timeout=timeout, headers={"User-Agent": "ARARAS-MT/1.0"})
            r.raise_for_status()
            root = ET.fromstring(r.content)
        except Exception as exc:  # noqa: BLE001
            log.warning("RSS imprensa falhou (%s): %s", termo[:40], exc)
            continue

        items = root.findall(".//item")[:max_n]
        for it in items:
            title = _norm((it.findtext("title") or ""))
            link = _norm((it.findtext("link") or ""))
            pub = _norm((it.findtext("pubDate") or ""))
            desc = _norm(re.sub(r"<[^>]+>", " ", it.findtext("description") or ""))
            uid = _uid("imprensa", title, link)
            if uid in seen or not title:
                continue
            seen.add(uid)
            blob = f"{title} {desc}"
            score, tags = _score_relevancia(blob, cfg)
            if score <= 0:
                score = 5.0  # manter sinal fraco de imprensa para triagem
            rows.append(
                {
                    "uid": uid,
                    "fonte": "IMPRENSA",
                    "consulta": termo,
                    "data_publicacao": pub,
                    "titulo": title[:200],
                    "municipios_mencionados": _extrair_municipios(blob),
                    "pagina": None,
                    "diario_id": None,
                    "pdf_id": None,
                    "url": link,
                    "score_relevancia": score,
                    "tags": "; ".join(tags) if tags else "imprensa",
                    "trecho": desc[:500],
                    "coletado_em": datetime.now().isoformat(timespec="seconds"),
                }
            )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("score_relevancia", ascending=False).reset_index(drop=True)


def run_busca_decretos(
    *,
    dias_retroativos: int | None = None,
    pages: int | None = None,
    incluir_imprensa: bool = True,
    persistir: bool = True,
) -> dict[str, Any]:
    """Orquestra IOMAT (+ imprensa), filtra, persiste e gera markdown."""
    cfg = load_config()
    iomat_df = buscar_iomat(pages=pages, cfg=cfg)
    imp_df = buscar_imprensa(cfg=cfg) if incluir_imprensa else pd.DataFrame()

    frames = [d for d in (iomat_df, imp_df) if d is not None and not d.empty]
    if not frames:
        return {"ok": False, "n": 0, "motivo": "Nenhum resultado nesta rodada.", "dataframe": pd.DataFrame()}

    df = pd.concat(frames, ignore_index=True)
    # dedup por uid
    df = df.drop_duplicates(subset=["uid"], keep="first")

    if dias_retroativos and "data_publicacao" in df.columns:
        # IOMAT usa YYYY-MM-DD; imprensa usa RFC822 — filtrar só IOMAT por data ISO
        mask_iso = df["data_publicacao"].astype(str).str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)
        cutoff = (pd.Timestamp.today().normalize() - pd.Timedelta(days=int(dias_retroativos))).strftime("%Y-%m-%d")
        keep = (~mask_iso) | (df["data_publicacao"].astype(str) >= cutoff)
        df = df.loc[keep].copy()

    df = df.sort_values(["fonte", "score_relevancia", "data_publicacao"], ascending=[True, False, False])
    tabela = str((cfg.get("saida") or {}).get("tabela_sqlite") or _TABLE_DEFAULT)

    if persistir and not df.empty:
        try:
            prev = None
            try:
                from sisclima.core.db import read_table, table_exists

                if table_exists(tabela):
                    prev = read_table(tabela)
            except Exception:  # noqa: BLE001
                prev = None
            if prev is not None and not prev.empty and "uid" in prev.columns:
                merged = pd.concat([prev, df], ignore_index=True).drop_duplicates(subset=["uid"], keep="last")
            else:
                merged = df
            write_df(merged, tabela)
            log.info("Persistidos %s registros em %s (total acumulado %s)", len(df), tabela, len(merged))
        except Exception as exc:  # noqa: BLE001
            log.warning("Falha ao persistir %s: %s", tabela, exc)

    md = format_relatorio_md(df, cfg=cfg)
    out_dir = ROOT / str((cfg.get("saida") or {}).get("markdown_dir") or "docs/apresentacoes")
    prefix = str((cfg.get("saida") or {}).get("markdown_prefix") or "Decretos_Emergencia_ARARAS")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{prefix}_{date.today().isoformat()}.md"
    path.write_text(md, encoding="utf-8")

    return {
        "ok": True,
        "n": int(len(df)),
        "n_iomat": int(len(iomat_df)) if iomat_df is not None else 0,
        "n_imprensa": int(len(imp_df)) if imp_df is not None else 0,
        "tabela": tabela,
        "markdown": str(path),
        "dataframe": df,
    }


def format_relatorio_md(df: pd.DataFrame, *, cfg: dict[str, Any] | None = None) -> str:
    cfg = cfg or load_config()
    max_n = int((cfg.get("saida") or {}).get("max_itens_relatorio") or 40)
    tema = str(cfg.get("tema") or "Decretos de emergência — ARARAS MT")
    linhas = [
        f"# {tema}",
        "",
        f"Gerado em {datetime.now().strftime('%d/%m/%Y às %Hh%M')}.",
        "",
        "> Fonte oficial prioritária: **IOMAT**. Itens de imprensa são sinais auxiliares e exigem validação no Diário Oficial antes de uso institucional.",
        "",
        f"Total nesta rodada: **{len(df)}** (exibindo até {max_n}).",
        "",
    ]
    if df.empty:
        linhas.append("_Nenhum ato relevante nesta rodada._")
        return "\n".join(linhas)

    work = df.head(max_n)
    for fonte in ("IOMAT", "IMPRENSA"):
        sub = work[work["fonte"] == fonte]
        if sub.empty:
            continue
        linhas.append(f"## {fonte}")
        linhas.append("")
        for _, row in sub.iterrows():
            titulo = row.get("titulo") or "—"
            data = row.get("data_publicacao") or "—"
            url = row.get("url") or ""
            tags = row.get("tags") or ""
            mun = row.get("municipios_mencionados") or ""
            score = row.get("score_relevancia")
            linhas.append(f"### {titulo}")
            linhas.append(f"- Data: {data}")
            if mun:
                linhas.append(f"- Municípios mencionados: {mun}")
            if tags:
                linhas.append(f"- Tags: {tags}")
            linhas.append(f"- Score: {score}")
            if url:
                linhas.append(f"- Link: {url}")
            trecho = row.get("trecho") or ""
            if trecho:
                linhas.append(f"- Trecho: {trecho[:320]}…")
            linhas.append("")
    linhas.append("---")
    linhas.append("_Agente ARARAS MT — busca IOMAT/imprensa de decretos de emergência._")
    return "\n".join(linhas)
