# -*- coding: utf-8 -*-
"""Recorte territorial fixo: Estado de Mato Grosso (UF 51).

O ARARAS MT opera sempre sobre MT, independentemente da localização física
do operador (ex.: viagem ao RS). Não confundir com Mato Grosso do Sul (MS).
"""
from __future__ import annotations

import re
import unicodedata

RECORTE_UF = "MT"
RECORTE_NOME = "Mato Grosso"

_MS_PATTERN = re.compile(r"mato\s+grosso\s+do\s+sul", re.I)
_MT_MESO = re.compile(r"mato[\s-]?grossense", re.I)
_MT_ESTADO = re.compile(r"(?<![a-z])mato\s+grosso(?!\s+do\s+sul)", re.I)


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text or ""))
    t = t.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", t).strip()


def alerta_abrange_mato_grosso(text: str) -> bool:
    """True se o texto descreve abrangência em MT (não MS)."""
    raw = str(text or "")
    if not raw.strip():
        return False
    sem_ms = _MS_PATTERN.sub(" ", raw)
    blob = _norm(sem_ms).lower()
    if _MT_MESO.search(blob):
        return True
    if _MT_ESTADO.search(blob):
        return True
    return False


def extrair_areas_mato_grosso(area: str) -> str:
    """Extrai trechos da área INMET referentes a MT (mesorregiões ou menções explícitas)."""
    raw = str(area or "").strip()
    if not raw:
        return ""
    prefix = "Aviso para as Áreas:"
    body = raw.split(prefix, 1)[-1].strip() if prefix in raw else raw
    partes = [p.strip() for p in body.split(",") if p.strip()]
    mt_partes = [p for p in partes if alerta_abrange_mato_grosso(p)]
    if mt_partes:
        return "; ".join(mt_partes[:8])
    if alerta_abrange_mato_grosso(body):
        return body[:180]
    return ""
