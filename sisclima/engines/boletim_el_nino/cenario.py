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


def semana_iso(hoje: date | None = None) -> dict[str, Any]:
    d = hoje or date.today()
    iso = d.isocalendar()
    inicio = d - timedelta(days=d.weekday())
    fim = inicio + timedelta(days=6)
    gerado = datetime.now()
    return {
        "ano": int(iso.year),
        "semana": int(iso.week),
        "rotulo": f"SE {iso.week:02d}/{iso.year}",
        "inicio": inicio.isoformat(),
        "fim": fim.isoformat(),
        "periodo_pt": (
            f"{inicio.day:02d} a {fim.day:02d} de {_MESES[inicio.month]} de {iso.year}"
        ),
        "gerado_em": gerado.isoformat(timespec="minutes"),
        "gerado_em_pt": gerado.strftime("%d/%m/%Y às %Hh%M"),
    }
