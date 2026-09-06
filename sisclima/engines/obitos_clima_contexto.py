# -*- coding: utf-8 -*-
"""Óbitos SIM em grupos potencialmente sensíveis a extremos térmicos — análise exploratória."""
from __future__ import annotations

from typing import Any

import pandas as pd

from sisclima.core.db import read_table, table_exists
from sisclima.engines.saude_calor_consolida import DICIONARIO_BASE

# Nomes públicos (nunca expor identificadores de DW/views no boletim)
_ROTULO_GRUPO = {
    "sensivel_calor_filtro_dw": "grupos potencialmente sensíveis (filtro operacional)",
    "calor_direto": "calor direto (T67/X30)",
    "desidratacao": "desidratação / hidroeletrolítico",
    "cardiovascular": "cardiovascular (I00–I99)",
    "respiratorio": "respiratório (J00–J99)",
    "renal": "renal / geniturinário (N00–N99)",
    "metabolico": "endócrino-metabólico (E10–E14)",
}

METODOLOGIA_OBITOS_CLIMA_MD = """
### Metodologia — mortalidade (SIM) potencialmente sensível a extremos térmicos

**Natureza da análise.** Contagem exploratória de óbitos do Sistema de Informações sobre
Mortalidade (SIM) em grupos de CID-10 amplos, associados na literatura a extremos térmicos.
**Não** constitui estimativa de mortalidade atribuível ao clima nem prova de causalidade
individual.

**Grupos CID (referência operacional)**
- Calor direto: T67, X30
- Desidratação / distúrbio hidroeletrolítico: E86, E87
- Cardiovascular: I00–I99
- Respiratório: J00–J99
- Renal / geniturinário: N00–N99
- Endócrino-metabólico: E10–E14 (quando aplicável)

**Limitações**
- Capítulos I/J/N/E são amplos; o total bruto **não** deve ser lido como óbitos “por calor”.
- Defasagem do SIM é esperada (semanas a meses). Ausência de registro ≠ ausência de óbito.
- Uso na Sala: tendência e vigilância; **não** como gatilho operacional isolado nesta rodada.
""".strip()


def _serie_estado() -> pd.DataFrame:
    if not table_exists("sim_obitos_calor_estado_serie_v6"):
        return pd.DataFrame()
    return read_table("sim_obitos_calor_estado_serie_v6")


def _municipal() -> pd.DataFrame:
    if not table_exists("sim_obitos_calor_municipal_v6"):
        return pd.DataFrame()
    return read_table("sim_obitos_calor_municipal_v6")


def _ibge7(val: object) -> str:
    digits = "".join(ch for ch in str(val or "") if ch.isdigit())
    return digits.zfill(7)[:7] if digits else ""


def _classificar_territorio(cod: str) -> str:
    if not cod or len(cod) < 2:
        return "invalido"
    if cod.startswith("51") and len(cod) == 7 and not cod.startswith("051"):
        return "mt_valido"
    if cod.startswith("051") or cod in {"0000000", "9999999"}:
        return "residencia_desconhecida_ou_agregado"
    if not cod.startswith("51"):
        return "fora_mt"
    return "invalido"


def _rotulo_grupo(chave: str) -> str:
    k = str(chave or "").strip()
    if k in _ROTULO_GRUPO:
        return _ROTULO_GRUPO[k]
    if "filtro" in k.casefold() or k.endswith("_dw") or "serie_v" in k.casefold():
        return "grupos potencialmente sensíveis (agregado operacional)"
    return k.replace("_", " ")


def resumo_obitos_clima() -> dict[str, Any]:
    serie = _serie_estado()
    mun = _municipal()
    total_serie = 0
    mes_ini = "—"
    mes_fim = "—"
    por_grupo: dict[str, int] = {}
    if serie is not None and not serie.empty and "obitos" in serie.columns:
        s = serie.copy()
        s["obitos"] = pd.to_numeric(s["obitos"], errors="coerce").fillna(0)
        total_serie = int(s["obitos"].sum())
        if "mes" in s.columns and s["mes"].notna().any():
            meses = sorted(s["mes"].astype(str).unique())
            mes_ini, mes_fim = meses[0], meses[-1]
        if "grupo_obito_calor" in s.columns:
            raw = s.groupby("grupo_obito_calor", dropna=False)["obitos"].sum().astype(int).to_dict()
            por_grupo = {_rotulo_grupo(k): int(v) for k, v in raw.items()}

    total_mun = 0
    n_mt = 0
    n_outros = 0
    n_desconhecido = 0
    n_fora = 0
    if mun is not None and not mun.empty and "obitos" in mun.columns:
        m = mun.copy()
        m["obitos"] = pd.to_numeric(m["obitos"], errors="coerce").fillna(0)
        m["cod7"] = m["cod_ibge"].map(_ibge7) if "cod_ibge" in m.columns else ""
        m["terr"] = m["cod7"].map(_classificar_territorio)
        total_mun = int(m["obitos"].sum())
        mt = m[m["terr"] == "mt_valido"]
        n_mt = int(mt.loc[mt["obitos"] > 0, "cod7"].nunique()) if not mt.empty else 0
        n_desconhecido = int(m.loc[m["terr"] == "residencia_desconhecida_ou_agregado", "cod7"].nunique())
        n_fora = int(m.loc[m["terr"] == "fora_mt", "cod7"].nunique())
        n_outros = int(m.loc[m["terr"] == "invalido", "cod7"].nunique())

    dic = [d for d in DICIONARIO_BASE if str(d.get("fonte")) == "SIM"]
    md = _markdown_boletim(
        total_serie=total_serie,
        mes_ini=mes_ini,
        mes_fim=mes_fim,
        total_mun=total_mun,
        n_mt=n_mt,
        n_desconhecido=n_desconhecido,
        n_fora=n_fora,
        n_outros=n_outros,
        por_grupo=por_grupo,
    )
    return {
        "ok": bool(total_serie or total_mun),
        "serie": serie if serie is not None else pd.DataFrame(),
        "municipal": mun if mun is not None else pd.DataFrame(),
        "total_serie": total_serie,
        "total_municipal": total_mun,
        "n_municipios_com_obito": n_mt,
        "n_municipios_mt_validos": n_mt,
        "n_residencia_desconhecida": n_desconhecido,
        "n_fora_mt": n_fora,
        "n_codigos_invalidos": n_outros,
        "periodo_inicio": mes_ini,
        "periodo_fim": mes_fim,
        "ultimo_mes": mes_fim,
        "por_grupo": por_grupo,
        "dicionario_sim": dic,
        "metodologia_md": METODOLOGIA_OBITOS_CLIMA_MD,
        "narrativa": md.replace("\n", " "),
        "markdown_boletim": md,
        "modulo_exploratorio": True,
    }


def _markdown_boletim(
    *,
    total_serie: int,
    mes_ini: str,
    mes_fim: str,
    total_mun: int,
    n_mt: int,
    n_desconhecido: int,
    n_fora: int,
    n_outros: int,
    por_grupo: dict[str, int],
) -> str:
    """Corpo principal: curto, exploratório, sem KPI de atribuição climática."""
    extras = []
    if n_desconhecido:
        extras.append(f"{n_desconhecido} código(s) de residência desconhecida/agregada")
    if n_fora:
        extras.append(f"{n_fora} fora de MT")
    if n_outros:
        extras.append(f"{n_outros} inválido(s)")
    extra_txt = f" · além disso: {'; '.join(extras)}" if extras else ""
    return "\n".join(
        [
            "### Monitoramento de mortalidade (SIM) — módulo exploratório",
            "",
            "Módulo em **validação metodológica**; **não utilizado como gatilho operacional** nesta rodada.",
            "",
            f"- **Período analisado:** {mes_ini}–{mes_fim}.",
            f"- Contagem exploratória em grupos de causas **potencialmente sensíveis a extremos térmicos** "
            f"(capítulos amplos I/J/N/E e calor direto): volume estadual consolidado na série — "
            f"leitura ecológica, **sem** estimativa de mortalidade atribuível ao clima.",
            f"- Recorte municipal com código IBGE de MT válido: **{n_mt}** município(s) "
            f"(universo operacional do boletim: 142){extra_txt}.",
            "- Detalhamento de CID, filtros e série completa: **anexo técnico / painel**.",
            "",
            "Fonte: SIM/DATASUS via consolidação SES-MT. Associação temporal/espacial ≠ causalidade.",
        ]
    )
