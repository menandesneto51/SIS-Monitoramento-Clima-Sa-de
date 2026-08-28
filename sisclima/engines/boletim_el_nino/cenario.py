# -*- coding: utf-8 -*-
"""Utilitários de calendário e cenário oficial."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from sisclima.core.config import ROOT
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

CENARIO_PATH = ROOT / "config" / "painel_el_nino.yaml"

_MESES = (
    "",
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
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


def semana_sinan(hoje: date | None = None) -> dict[str, Any]:
    """Semana epidemiológica SINAN (domingo a sábado; 1ª semana contém 4 de janeiro).

    Fonte: calendário oficial do Ministério da Saúde / SINAN.
    Não usar isocalendar() (ISO, segunda a domingo): na segunda a semana ISO
    já avança, enquanto a SE SINAN só muda no domingo.
    """
    d = hoje or date.today()
    inicio = d - timedelta(days=(d.weekday() + 1) % 7)
    fim = inicio + timedelta(days=6)
    ancora = inicio + timedelta(days=3)  # quarta-feira: maior número de dias no ano
    ano = ancora.year
    jan4 = date(ano, 1, 4)
    se1 = jan4 - timedelta(days=(jan4.weekday() + 1) % 7)
    semana = ((inicio - se1).days // 7) + 1
    gerado = datetime.now()
    if inicio.month == fim.month:
        periodo = f"{inicio.day:02d} a {fim.day:02d} de {_MESES[inicio.month]} de {ano}"
    else:
        periodo = (
            f"{inicio.day:02d} de {_MESES[inicio.month]} a "
            f"{fim.day:02d} de {_MESES[fim.month]} de {ano}"
        )
    return {
        "ano": int(ano),
        "semana": int(semana),
        "rotulo": f"SE {semana:02d}/{ano}",
        "inicio": inicio.isoformat(),
        "fim": fim.isoformat(),
        "periodo_pt": periodo,
        "gerado_em": gerado.isoformat(timespec="minutes"),
        "gerado_em_pt": gerado.strftime("%d/%m/%Y às %Hh%M"),
    }


def semana_iso(hoje: date | None = None) -> dict[str, Any]:
    """Rótulo da semana do boletim: calendário SINAN (não ISO)."""
    return semana_sinan(hoje)
