# -*- coding: utf-8 -*-
"""Óbitos SIM em grupos sensíveis ao clima/calor — resumo e metodologia pública."""
from __future__ import annotations

from typing import Any

import pandas as pd

from sisclima.core.db import read_table, table_exists
from sisclima.engines.saude_calor_consolida import DICIONARIO_BASE


METODOLOGIA_OBITOS_CLIMA_MD = """
### Metodologia — óbitos sensíveis ao calor/clima (SIM)

**O que é contabilizado.** Óbitos do Sistema de Informações sobre Mortalidade (SIM/DATASUS),
via Data Warehouse SES-MT quando disponível, filtrados por grupos de CID-10 associados
epidemiologicamente a extremos térmicos e suas vias intermediárias — **não** são “óbitos
causados pelo clima” em sentido jurídico ou causal individual.

**Grupos CID utilizados no ARARAS MT**
- **Calor direto:** T67 (efeitos do calor e da luz), X30 (exposição a calor natural excessivo)
- **Desidratação / distúrbio hidroeletrolítico:** E86, E87
- **Cardiovascular:** capítulo I00–I99 (quando o filtro operacional do DW incluir essas causas)
- **Respiratório:** capítulo J00–J99
- **Renal / geniturinário:** capítulo N00–N99
- **Endócrino-metabólico (diabetes e afins):** E10–E14, quando aplicável ao filtro

**Como ler no painel**
- A série estadual mensal (`sim_obitos_calor_estado_serie_v6`) mostra volume por mês e grupo.
- O mapa/tabela municipal soma o recorte operacional da última consolidação — cobertura e
  classificação CID dependem da qualidade do DW e da data de processamento.
- **Ausência de registro ≠ ausência de óbito**; defasagem do SIM é esperada (semanas a meses).

**Limitações**
- Associação ecológica e temporal: útil para vigilância e priorização, **não prova** que o
  clima foi a causa do óbito individual.
- Filtros do DW podem agregar em `sensivel_calor_filtro_dw` quando o CID bruto não está
  disponível na base operacional.
- Não substitui investigação de óbito, atestado médico nem análise de excesso de mortalidade
  com modelo estatístico formal (ex.: série temporal com confounders).

**Uso recomendado na Sala de Situação:** acompanhar tendência mensal e territorial junto com
calor, fumaça/PM2,5 e pressão assistencial; acionar investigação quando houver pico atípico
coincidente com onda de calor ou episódio de fumaça.
""".strip()


def _serie_estado() -> pd.DataFrame:
    if not table_exists("sim_obitos_calor_estado_serie_v6"):
        return pd.DataFrame()
    return read_table("sim_obitos_calor_estado_serie_v6")


def _municipal() -> pd.DataFrame:
    if not table_exists("sim_obitos_calor_municipal_v6"):
        return pd.DataFrame()
    return read_table("sim_obitos_calor_municipal_v6")


def resumo_obitos_clima() -> dict[str, Any]:
    serie = _serie_estado()
    mun = _municipal()
    total_serie = 0
    ultimo_mes = "—"
    por_grupo: dict[str, int] = {}
    if serie is not None and not serie.empty and "obitos" in serie.columns:
        s = serie.copy()
        s["obitos"] = pd.to_numeric(s["obitos"], errors="coerce").fillna(0)
        total_serie = int(s["obitos"].sum())
        if "mes" in s.columns and s["mes"].notna().any():
            ultimo_mes = str(sorted(s["mes"].astype(str).unique())[-1])
        if "grupo_obito_calor" in s.columns:
            por_grupo = (
                s.groupby("grupo_obito_calor", dropna=False)["obitos"].sum().astype(int).to_dict()
            )

    total_mun = 0
    n_mun = 0
    if mun is not None and not mun.empty and "obitos" in mun.columns:
        m = mun.copy()
        m["obitos"] = pd.to_numeric(m["obitos"], errors="coerce").fillna(0)
        total_mun = int(m["obitos"].sum())
        if "cod_ibge" in m.columns:
            n_mun = int(m.loc[m["obitos"] > 0, "cod_ibge"].astype(str).nunique())

    dic = [d for d in DICIONARIO_BASE if str(d.get("fonte")) == "SIM"]
    narrativa = (
        f"Óbitos SIM em grupos sensíveis ao calor/clima: {total_serie} na série estadual "
        f"(último mês com dado: {ultimo_mes}). "
        f"Recorte municipal consolidado: {total_mun} óbitos em {n_mun} municípios com registro. "
        "Leitura ecológica — não implica causalidade individual."
    )
    return {
        "ok": bool(total_serie or total_mun),
        "serie": serie if serie is not None else pd.DataFrame(),
        "municipal": mun if mun is not None else pd.DataFrame(),
        "total_serie": total_serie,
        "total_municipal": total_mun,
        "n_municipios_com_obito": n_mun,
        "ultimo_mes": ultimo_mes,
        "por_grupo": por_grupo,
        "dicionario_sim": dic,
        "metodologia_md": METODOLOGIA_OBITOS_CLIMA_MD,
        "narrativa": narrativa,
        "markdown_boletim": _markdown_boletim(
            total_serie, ultimo_mes, total_mun, n_mun, por_grupo
        ),
    }


def _markdown_boletim(
    total_serie: int,
    ultimo_mes: str,
    total_mun: int,
    n_mun: int,
    por_grupo: dict[str, int],
) -> str:
    linhas = [
        "### Óbitos sensíveis ao calor/clima (SIM)",
        "",
        f"- Série estadual consolidada: **{total_serie}** óbitos no período disponível "
        f"(último mês: **{ultimo_mes}**).",
        f"- Recorte municipal da última consolidação: **{total_mun}** óbitos em **{n_mun}** municípios.",
    ]
    if por_grupo:
        partes = ", ".join(f"{k}: {v}" for k, v in sorted(por_grupo.items(), key=lambda x: -x[1]))
        linhas.append(f"- Por grupo operacional: {partes}.")
    linhas.extend(
        [
            "",
            "**Metodologia (resumo):** contagem de óbitos SIM com CID em grupos associados "
            "epidemiologicamente a extremos térmicos (T67/X30, desidratação, cardio, respiratório, "
            "renal, metabólico, conforme filtro do DW). Associação ecológica — **não** afirma "
            "causalidade individual. Detalhe completo na seção de notas metodológicas e no painel "
            "(aba Óbitos e clima).",
        ]
    )
    return "\n".join(linhas)
