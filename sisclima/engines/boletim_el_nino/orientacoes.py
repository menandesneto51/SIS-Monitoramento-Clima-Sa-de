# -*- coding: utf-8 -*-
"""Orientações operacionais por cenário climático."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from sisclima.core.config import ROOT
from sisclima.core.logging_utils import get_logger
from sisclima.engines.boletim_el_nino.constants import INDISPONIVEL
from sisclima.engines.boletim_el_nino.formatters import fmt_frac, fmt_int, md_table

log = get_logger(__name__)

ORIENTACOES_PATH = ROOT / "config" / "boletim_el_nino_orientacoes.yaml"


def load_orientacoes_config(path: Path | None = None) -> dict[str, Any]:
    target = path or ORIENTACOES_PATH
    try:
        if not target.exists():
            return {}
        data = yaml.safe_load(target.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001
        log.warning("Catálogo de orientações indisponível: %s", exc)
        return {}


def _resolve_situacao(snap: dict[str, Any], campo: str | None) -> str:
    if not campo:
        return INDISPONIVEL
    agr = snap.get("agravos_monitorados") or {}
    n = snap.get("n_municipios")
    if campo == "municipios_hidro_alerta":
        v = (agr.get("hidrorelacionados") or {}).get("municipios_hidro_alerta")
        return f"{v} municípios com sinal hidrológico de alerta no recorte disponível." if v is not None else INDISPONIVEL
    if campo == "municipios_calor_seco":
        v = (agr.get("calor_desidratacao") or {}).get("municipios_calor_seco")
        return f"{v} municípios em condição combinada de calor seco (Tmáx ≥ 37 °C e UR ≤ 30%)." if v is not None else INDISPONIVEL
    if campo == "n_pm25_25":
        v = snap.get("n_pm25_25")
        if v is None:
            return INDISPONIVEL
        return f"{fmt_frac(v, n)} municípios com PM2,5 ≥ 25 µg/m³."
    val = snap.get(campo)
    if val is None:
        return INDISPONIVEL
    return str(val)


def _quadro_cenario(cfg: dict[str, Any], snap: dict[str, Any]) -> str:
    acoes = cfg.get("acoes_municipio") or {}
    acoes_md = "\n".join(f"  - **{k}:** {v}" for k, v in acoes.items())
    situacao = _resolve_situacao(snap, cfg.get("situacao_campo"))
    ses = str(cfg.get("acoes_ses") or "—")
    if "{n_crit}" in ses or "vermelho/roxa" in ses:
        n_crit = snap.get("n_vermelha_roxa")
        ses = ses.replace("{n_crit}", str(n_crit) if n_crit is not None else INDISPONIVEL)
    return f"""
### Cenário: {cfg.get('nome', '—')}

| Campo | Conteúdo |
| --- | --- |
| Situação observada | {situacao} |
| Critérios/indicadores | {cfg.get('criterios', '—')} |
| Possíveis repercussões em saúde | {cfg.get('repercussao', '—')} |
| Populações potencialmente mais vulneráveis | {cfg.get('vulneraveis', '—')} |

**Ações recomendadas ao município**
{acoes_md}

**Ações recomendadas à Secretaria de Estado de Saúde (SES-MT)**
- {ses}

**Referências técnicas:** {cfg.get('referencias', '—')}
"""


def orientacoes_por_cenario(snap: dict[str, Any], config: dict[str, Any] | None = None) -> str:
    cfg = config or load_orientacoes_config()
    cenarios = cfg.get("cenarios") or []
    if not cenarios:
        return "_Catálogo de orientações indisponível nesta rodada._"
    return "\n".join(_quadro_cenario(c, snap) for c in cenarios if isinstance(c, dict))


def matriz_clima_saude_acao(snap: dict[str, Any]) -> str:
    """Blocos por cenário — evita tabela larga de seis colunas."""
    if not snap.get("disponivel"):
        return f"_{INDISPONIVEL}_"

    n = snap.get("n_municipios")
    niveis = snap.get("niveis") or {}
    n25 = snap.get("n_pm25_25")
    blocos: list[str] = []

    if niveis.get("roxa") or niveis.get("vermelha"):
        blocos.append(
            "**Calor extremo**\n"
            "- Nível atual: classes vermelha e roxa\n"
            "- Impactos potenciais: desidratação e agravamento cardiorrespiratório\n"
            "- Insumos a revisar: soluções de reidratação oral e insumos de suporte conforme protocolos\n"
            "- Ação municipal: avaliar capacidade assistencial e comunicação de risco\n"
            "- Ação SES-MT: apoiar regionais prioritárias"
        )
    if n25:
        blocos.append(
            "**Fumaça e qualidade do ar**\n"
            f"- Situação: {fmt_frac(n25, n)} municípios com PM2,5 ≥ 25 µg/m³\n"
            "- Impactos potenciais: agravamento de doenças respiratórias\n"
            "- Insumos a revisar: insumos respiratórios conforme protocolo\n"
            "- Ação municipal: orientar redução de exposição e monitorar SRAG conforme protocolos\n"
            "- Ação SES-MT: consolidar casos e orientar regionais"
        )
    if not blocos:
        return "_Sem cenário prioritário para matriz nesta rodada._"
    return "\n\n".join(blocos)


def impactos_potenciais_saude(config: dict[str, Any] | None = None) -> str:
    cfg = config or load_orientacoes_config()
    items = cfg.get("impactos_saude") or []
    if not items:
        return md_table(
            ["Evento", "Exposição", "Agravos a monitorar", "Indicadores disponíveis"],
            [["—", "—", "—", "—"]],
        )
    rows = [
        [str(i.get("evento", "—")), str(i.get("exposicao", "—")), str(i.get("agravos", "—")), str(i.get("indicadores", "—"))]
        for i in items
        if isinstance(i, dict)
    ]
    return md_table(["Evento", "Exposição", "Agravos a monitorar", "Indicadores disponíveis"], rows)
