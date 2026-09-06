# -*- coding: utf-8 -*-
"""Ações acionáveis para a Sala — orientações + implantação Plano (sem inventar numerador)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sisclima.core.config import ROOT
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

COBRANCA_DIR = ROOT / "docs" / "apresentacoes" / "cobranca_emails"

_AREA_ARQUIVO = {
    "cievs": "CIEVS",
    "atencao_saude": "Atenção à Saúde",
    "vigilancia_ambiental": "Vigilância Ambiental",
    "assistencia_farmaceutica": "Assistência Farmacêutica",
    "imunizacao": "Imunização",
    "vigiagua": "Vigiagua",
    "vigilancia_sanitaria": "Vigilância Sanitária",
    "saude_trabalhador": "Saúde do Trabalhador",
    "logistica": "Logística",
}


def _ler_resumo_cobranca(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        txt = path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("Falha ao ler cobrança %s: %s", path, exc)
        return None
    # Bloco da área (primeiro assunto) ou arquivo único
    m_pend = re.search(
        r"Pendências desta área:\s*(\d+)\s+para informar[^;]*;\s*(\d+)\s+aguardando[^;]*;\s*(\d+)\s+com carga defasada",
        txt,
        re.I,
    )
    prioridade: list[str] = []
    bloco = re.search(
        r"Prioridade desta semana[^\n]*:\s*((?:-\s*IND-[^\n]+\n?)+)",
        txt,
        re.I,
    )
    if bloco:
        for line in bloco.group(1).splitlines():
            line = line.strip()
            if line.startswith("-"):
                prioridade.append(line.lstrip("- ").strip())
    if not m_pend and not prioridade:
        return None
    return {
        "informar": int(m_pend.group(1)) if m_pend else None,
        "aguardando": int(m_pend.group(2)) if m_pend else None,
        "defasada": int(m_pend.group(3)) if m_pend else None,
        "prioridade": prioridade[:3],
    }


def resumo_implantacao_plano(*, cobranca_dir: Path | None = None) -> dict[str, Any]:
    """Lê artefatos de cobrança — não inventa numeradores de indicadores."""
    base = cobranca_dir or COBRANCA_DIR
    areas: list[dict[str, Any]] = []
    total_informar = 0
    for stem, rotulo in _AREA_ARQUIVO.items():
        path = base / f"{stem}.txt"
        r = _ler_resumo_cobranca(path)
        if not r:
            continue
        informar = int(r.get("informar") or 0)
        total_informar += informar
        areas.append(
            {
                "area": rotulo,
                "arquivo": path.name,
                "informar": r.get("informar"),
                "aguardando": r.get("aguardando"),
                "defasada": r.get("defasada"),
                "prioridade": r.get("prioridade") or [],
            }
        )
    # Fallback: arquivo consolidado
    if not areas:
        todas = base / "_todas_as_areas.txt"
        r = _ler_resumo_cobranca(todas)
        if r:
            areas.append(
                {
                    "area": "Áreas técnicas (consolidado)",
                    "arquivo": todas.name,
                    "informar": r.get("informar"),
                    "aguardando": r.get("aguardando"),
                    "defasada": r.get("defasada"),
                    "prioridade": r.get("prioridade") or [],
                }
            )
            total_informar = int(r.get("informar") or 0)
    return {
        "ok": bool(areas),
        "areas": areas,
        "total_informar": total_informar,
        "fonte": "docs/apresentacoes/cobranca_emails",
        "nota": (
            "Evidência oficial = Sim + SEI no painel da Sala. "
            "Responder só por e-mail não fecha indicador. Não informar zero na ausência de dado."
        ),
    }


def markdown_acoes_sala(snap: dict[str, Any], *, max_bullets: int = 6) -> str:
    """Até 6 bullets: clima ativo + pendências de implantação do Plano."""
    from sisclima.engines.boletim_el_nino.formatters import fmt_frac, fmt_int

    bullets: list[str] = []
    n = snap.get("n_municipios")
    crit = snap.get("n_vermelha_roxa")
    proj = snap.get("niveis_projecao_7d") or {}
    proj_crit = int(proj.get("vermelha") or 0) + int(proj.get("roxa") or 0)
    n41 = int((snap.get("picos_termicos") or {}).get("n_tmax_41") or snap.get("n_tmax_41_semana") or 0)
    n25 = int(snap.get("n_pm25_25") or 0)

    if crit:
        bullets.append(
            f"**CIEVS / Regionais (24–48h):** reforçar articulação nos **{fmt_frac(crit, n)}** "
            f"vermelho/roxo; projeção ~7d sobe para **{fmt_frac(proj_crit, n)}**."
        )
    if n41:
        bullets.append(
            f"**Atenção à Saúde:** preparar capacidade assistencial onde houve pico ≥ 41 °C "
            f"({fmt_int(n41)} municípios na janela) — reidratação, grupos vulneráveis e "
            "orientação a trabalhadores expostos."
        )
    elif int(snap.get("n_tmax_37") or 0):
        bullets.append(
            f"**Atenção à Saúde:** calor ≥ 37 °C em **{fmt_frac(snap.get('n_tmax_37'), n)}** — "
            "manter orientação a idosos, gestantes e exposição ocupacional."
        )
    if n25:
        bullets.append(
            f"**Vigilância Ambiental / APS:** PM2,5 ≥ 25 µg/m³ em **{fmt_frac(n25, n)}** — "
            "redução de exposição e vigilância de sinais respiratórios na atenção primária."
        )

    impl = resumo_implantacao_plano()
    if impl.get("ok"):
        # Top 3 áreas com mais pendências "para informar"
        ranked = sorted(
            [a for a in impl["areas"] if a.get("informar")],
            key=lambda a: int(a.get("informar") or 0),
            reverse=True,
        )[:3]
        for a in ranked:
            if len(bullets) >= max_bullets:
                break
            pri = a.get("prioridade") or []
            tip = pri[0].split(":")[0].strip() if pri else "indicadores pendentes"
            bullets.append(
                f"**{a['area']} (até a próxima Sala):** {fmt_int(a.get('informar'))} indicador(es) "
                f"para informar no painel (ex.: {tip}). "
                f"{fmt_int(a.get('aguardando'))} aguardando fonte · {fmt_int(a.get('defasada'))} carga defasada."
            )
        if len(bullets) < max_bullets:
            bullets.append(
                f"**Comando / Sala:** evidência de implantação = **Sim + SEI** no painel Plano El Niño. "
                f"{impl['nota']}"
            )
    else:
        bullets.append(
            "**Plano El Niño:** base de indicadores sem leitura consolidada nesta rodada — "
            "áreas devem registrar evidência Sim+SEI no painel; e-mail sozinho não fecha indicador."
        )

    bullets = bullets[:max_bullets]
    if not bullets:
        return "_Sem ações priorizadas calculáveis nesta rodada._"
    return "\n".join(f"- {b}" for b in bullets)
