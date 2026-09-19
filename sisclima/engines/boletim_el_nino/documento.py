# -*- coding: utf-8 -*-
"""Montagem do documento Markdown do boletim semanal El Niño."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sisclima.core.config import ROOT
from sisclima.engines.boletim_el_nino.constants import (
    FOGO_SATELITE_REFERENCIA_CURTO,
    INDISPONIVEL,
    NAO_CALCULADO,
    TITULO_PRODUTO_ATUAL,
    TITULO_SALA_SITUACAO,
    SUBTITULO_SALA_SITUACAO,
    SUBTITULO_INSTITUCIONAL,
    USAR_TITULO_SALA_SITUACAO,
    NIVEL_LEGENDA,
    REFERENCIAS_PADRAO,
    SELDERIV,
    SELIND,
    SELOBS,
    SELPREV,
    SELPROJ,
    SELSAZ,
)
from sisclima.engines.boletim_el_nino.formatters import (
    bloco_tabela,
    expand_siglas,
    fmt_counts,
    fmt_date_pt,
    fmt_distribuicao_niveis,
    fmt_frac,
    fmt_int,
    fmt_metric_box,
    fmt_num,
    fmt_pareamento,
    fmt_plural,
    humanize_label,
    md_table,
    numerar_tabelas,
)
from sisclima.engines.boletim_el_nino.governanca import (
    articulacao_intersetorial,
    box_base_normativa,
    conclusao_tendencia,
    encaminhamentos,
    matriz_areas_ses,
    populacoes_prioritarias,
    saude_trabalhador,
    sintese_territorial,
)
from sisclima.engines.boletim_el_nino.interpretacao import (
    analisar_cenario_bloco,
    interpretar_fogo,
    interpretar_hidrologia,
    interpretar_medidor,
    interpretar_pm25,
    interpretar_temperatura,
    interpretar_tendencia,
    interpretar_umidade,
    leitura_integrada,
)
from sisclima.engines.boletim_el_nino.determinantes_projecao import quadro_determinantes_projecao
from sisclima.engines.predicao_skill_7d import documentacao_regra_projecao_md
from sisclima.engines.rit_multirisco import documentacao_rit_md
from sisclima.engines.boletim_el_nino.orientacoes import (
    _texto_calor_epidemiologico,
    impactos_potenciais_saude,
    matriz_clima_saude_acao,
    orientacoes_por_cenario,
)
from sisclima.engines.boletim_el_nino.prontidao import metodologia_indice_md
from sisclima.engines.boletim_el_nino.referencias import cite


class _FigCounter:
    """Numeração sequencial de figuras no corpo/anexo."""

    def __init__(self) -> None:
        self.n = 0

    def caption(self, titulo: str) -> str:
        self.n += 1
        return f"**Figura {self.n} – {titulo}**"


def _narrativa(cenario: dict[str, Any], chave: str, fallback: str = "") -> str:
    bloco = cenario.get("narrativa") or {}
    return str(bloco.get(chave) or fallback or INDISPONIVEL).strip()


def _fmt_ext(ext: dict[str, Any] | None, col: str, suf: str = "", *, inteiro: bool = False) -> str:
    if not ext:
        return INDISPONIVEL
    mun = ext.get("municipio") or "—"
    val = fmt_int(ext.get(col)) if inteiro else fmt_num(ext.get(col), 1, suf)
    return f"{mun} ({val})"


def _cel_extremo(n_ext: Any, n: Any, criterio: str) -> str:
    if n_ext is None:
        return INDISPONIVEL
    return f"{fmt_frac(n_ext, n)} {criterio}"


def _bloco_irm_compostos(snap: dict[str, Any]) -> str:
    """Bloco opcional IRM + compostos leves (capacidade ≠ elevação de RIT)."""
    c = snap.get("compostos") or {}
    rit = snap.get("rit") or {}
    if not c.get("disponivel") and rit.get("irm_mediana") is None:
        return ""
    irm = c.get("irm_mediana")
    if irm is None:
        irm = rit.get("irm_mediana")
    n = c.get("n_municipios") or rit.get("n")
    n_gap = c.get("n_gap_fumaca_nebulizacao")
    n_pr = c.get("n_pressao_x_resiliencia")
    omit_rit = int((rit.get("n_pressao_omitida") or 0))
    linhas = [
        f"- **IRM mediano (capacidade CNES):** {fmt_num(irm, 0) if irm is not None else '—'} "
        f"(alto = melhor rede; no RIT entra só a fragilidade 100−IRM).",
    ]
    # Gap=0 sem discriminar qualidade: omitir do corpo (sem capacidade discriminatória)
    if n_gap is not None and n is not None and int(n_gap) > 0:
        linhas.append(
            f"- **Gap fumaça × nebulização:** {fmt_frac(n_gap, n)} municípios com sinal de fumaça e nebulizadores = 0."
        )
    if n_pr is not None and n is not None:
        linhas.append(
            f"- **Indicador composto pressão × resiliência/IRM** (distinto do domínio pressão do RIT): "
            f"{fmt_frac(n_pr, n)} com tensão entre pressão assistencial e faixa do IRM."
        )
    if omit_rit:
        linhas.append(
            f"- **Domínio pressão omitido do RIT por defasagem:** {fmt_int(omit_rit)} municípios "
            f"(não confundir com o composto pressão × resiliência acima)."
        )
    return "### Capacidade de rede (IRM) e compostos\n\n" + "\n".join(linhas) + "\n"


def _leitura_faixa(
    mediana: Any,
    vmin: Any,
    vmax: Any,
    *,
    casas: int,
    suf: str,
    n_ext: Any,
    n: Any,
    criterio: str,
) -> str:
    partes = [f"mediana {fmt_num(mediana, casas, suf)}"]
    if vmin is not None or vmax is not None:
        partes.append(f"mín. {fmt_num(vmin, casas)} – máx. {fmt_num(vmax, casas, suf)}")
    if n_ext is not None:
        partes.append(f"{fmt_frac(n_ext, n)} {criterio}")
    return "; ".join(partes)


def _secao_agravos_dw(agr: dict[str, Any]) -> str:
    dw = agr.get("dw_epidemiologia") or {}
    if not dw or dw.get("status") == "indisponivel":
        return ""

    def _v(x: Any) -> str:
        return fmt_int(x) if x is not None else INDISPONIVEL

    janela = fmt_int(dw.get("janela_dias", 7))
    intox = dw.get("intoxicacao_fumaca") or {}
    intern = dw.get("internacao_indicasus") or dw.get("internacao_hospitalar") or {}
    grupos = intern.get("grupos_7d") or {}
    grupos_mes = intern.get("grupos_ultimo_mes_dw") or {}

    def _internacao_linha() -> str:
        total = intern.get("internacoes_total_7d")
        if total is not None:
            return (
                f"- **Internações IndicaSUS (janela {janela} dias):** total **{_v(total)}** · "
                f"respiratório/alérgico **{_v(grupos.get('resp_alergico'))}** · "
                f"desidratação/calor **{_v(grupos.get('desidratacao_calor'))}**."
            )
        mes_total = intern.get("internacoes_ultimo_mes_dw")
        if mes_total is not None:
            mes = intern.get("mes_competencia_dw") or "—"
            return (
                f"- **Internações IndicaSUS (competência {mes}):** total **{fmt_int(mes_total)}** · "
                f"respiratório/alérgico **{_v(grupos_mes.get('resp_alergico'))}** · "
                f"desidratação/calor **{_v(grupos_mes.get('desidratacao_calor'))}**. "
                f"_Janela de {janela} dias sem registros na base; exibido o mês competência disponível._"
            )
        data_max = intern.get("data_maxima_disponivel")
        status = str(intern.get("status") or "")
        if status in {"sem_dados_na_janela", "indisponivel"} and data_max:
            return (
                f"- **Internações IndicaSUS:** sem registros na janela de {janela} dias "
                f"(dado mais recente na base: **{data_max}**)."
            )
        return (
            "- **Internações IndicaSUS:** dados não estavam disponíveis para esta rodada "
            "(DW/tabela operacional vazia ou inacessível)."
        )

    esus = dw.get("esus_aps") or agr.get("esus_aps") or {}
    extras = dw.get("sinan_extras_clima") or {}
    por_agravo = extras.get("por_agravo_7d") or {}
    extras_line = ""
    if por_agravo:
        partes = [f"{k} **{_v(v)}**" for k, v in sorted(por_agravo.items(), key=lambda x: -int(x[1] or 0))]
        extras_line =             f"- **Agravos extras clima (SINAN/DW):** {'; '.join(partes)}."
    elif extras.get("fonte") == "indisponivel":
        extras_line = "- **Agravos extras clima (SINAN/DW):** indisponível nesta rodada."

    malaria = dw.get("sivep_malaria") or {}
    malaria_line = ""
    if malaria.get("casos_malaria_7d") is not None:
        malaria_line = (
            f"- **Malária (SIVEP/DW):** {_v(malaria.get('casos_malaria_7d'))} casos em "
            f"{_v(malaria.get('municipios_7d'))} município(s)"
            + (f" · janela `{malaria.get('janela')}`" if malaria.get("janela") else "")
            + " — base pode estar defasada; não substitui SRAG local."
        )

    sivep = dw.get("sivep_alergico_dda") or {}
    sivep_line = (
        f"- **SRAG:** {_v(sivep.get('casos_srag_7d'))} casos na janela · "
        f"fonte **{sivep.get('fonte') or '—'}** (preferencial: SIVEP local; DW só se local vazio)."
    )

    esus_lines: list[str] = []
    if esus.get("status") == "ativo" and int(esus.get("municipios") or 0) > 0:
        atraso = int(esus.get("atraso_dias") or 0)
        data_max_raw = str(esus.get("data_max_atendimento") or "—")
        if re.match(r"^\d{4}-\d{2}-\d{2}", data_max_raw):
            y, m, d = data_max_raw[:10].split("-")
            data_max = f"{d}/{m}/{y}"
        else:
            data_max = data_max_raw
        esus_lines = [
            "",
            "> **DADO ASSISTENCIAL DEFASADO**  ",
            f"> Última atualização: **{data_max}**  ",
            "> Não representa a situação corrente da SE em curso.",
            "",
            f"- **Atenção primária (Centralizador PEC/eSUS):** cadastro **{fmt_int(esus.get('cadastros'))}** · "
            f"asma **{fmt_int(esus.get('asma'))}** · idosos 60+ **{fmt_int(esus.get('idoso_60mais'))}** · "
            f"gestantes **{fmt_int(esus.get('gestante'))}** · "
            f"**{fmt_int(esus.get('municipios_vermelho_roxo'))}** municípios vermelho/roxo com cadastro.",
            f"- Status temporal: **DEFASADO** (última carga **{data_max}**, "
            f"atraso **{fmt_int(atraso)}** dia(s)). Usado só como contexto de vulnerabilidade/cobertura, "
            "**não** como pressão assistencial corrente.",
            "- Tabelas detalhadas de atendimento: **anexo técnico / painel**. "
            "Ausência de envio = **N/D** (≠ zero clínico).",
        ]

    return "\n".join(
        [
            "",
            f"### Epidemiologia operacional (janela {janela} dias)",
            "",
            f"- **Intoxicação exógena (sinal de fumaça):** {_v(intox.get('notificacoes_intox_total_7d'))} notificações; "
            f"**{_v(intox.get('notificacoes_fumaca_7d'))}** com sinal de fumaça.",
            _internacao_linha(),
            sivep_line,
            extras_line,
            malaria_line,
            *esus_lines,
        ]
    )


def _load_json(path: Path) -> dict[str, Any]:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return {}


def _secao_ondas_calor(
    snap: dict[str, Any],
    maps: dict[str, Any] | None = None,
    figs: _FigCounter | None = None,
) -> tuple[str, str]:
    """Ondas de calor — GeoCalor/EHF (Fiocruz) + operação ARARAS; sem nomenclatura STAR.

    Returns:
        (corpo_principal_md, anexo_series_md)
    """
    maps = maps or {}
    figs = figs or _FigCounter()
    n = snap.get("n_municipios")
    n_onda = snap.get("n_onda_calor")
    n_tmax = snap.get("n_tmax_37")
    ext = (snap.get("extremos") or {}).get("tmax") or {}
    tmax_max = ext.get("tmax")
    om_cui = maps.get("cuiaba_openmeteo_tmax_semana")
    picos = snap.get("picos_termicos") or {}
    cui_g = picos.get("cuiaba_grade") or {}
    linhas = [
        "",
        "### Ondas de calor",
        "",
        "Três conceitos distintos: (A) **calor seco combinado** (Tmáx ≥ 37 °C e UR ≤ 30%); "
        "(B) **onda de calor EHF observada** (EHF > 0 por ≥ 3 dias); "
        "(C) **projeção ARARAS ~7 dias** (componente térmico projetado). "
        "**Não substitui** avisos do INMET.",
        "",
    ]

    geo_md = str(snap.get("geocalor_fiocruz_md") or "").strip()
    if geo_md:
        geo_body = geo_md
        if geo_body.startswith("### "):
            geo_body = "\n".join(geo_body.splitlines()[1:]).lstrip("\n")
        linhas.extend(["### GeoCalor / EHF", "", geo_body])
    elif snap.get("geocalor_fiocruz_ok") is False:
        linhas.append(
            "### GeoCalor / EHF\n\nIndisponível nesta rodada — ver notas metodológicas.\n"
        )
    if maps.get("grafico_geocalor_ehf"):
        geo = snap.get("geocalor_fiocruz") or {}
        temp_ini = geo.get("temporada_inicio") or "—"
        temp_fim = geo.get("temporada_fim") or "—"
        jan_ini = geo.get("janela_inicio") or "—"
        jan_fim = geo.get("janela_fim") or "—"
        linhas.extend(
            [
                "",
                figs.caption(
                    "Municípios em dia de onda (EHF) — canal da temporada operacional e janela do boletim"
                ),
                "",
                f"![GeoCalor EHF]({maps.get('grafico_geocalor_ehf')})",
                "",
                f"Fonte: cálculo EHF estadual ARARAS (definição GeoCalor / Nairn & Fawcett). "
                f"Temporada operacional {temp_ini} a {temp_fim}; "
                f"janela do boletim destacada {jan_ini} a {jan_fim}. "
                f"Canal = P25–P75 móvel de 14 dias sobre a série operacional — "
                f"não substitui climatologia oficial de longo prazo.",
                "",
            ]
        )

    linhas.extend(["### Operação ARARAS (grade e classes)", ""])
    if picos.get("ok"):
        ini = picos.get("janela_inicio") or "—"
        fim = picos.get("janela_fim") or "—"
        n_mun = picos.get("n_municipios_janela") or n
        linhas.extend(
            [
                f"- **Picos da janela ({ini} a {fim}):** Tmáx máxima estadual **{fmt_num(picos.get('tmax_max_semana'), 1, ' °C')}** · "
                f"**{fmt_frac(picos.get('n_tmax_41'), n_mun)}** ≥ 41 °C · "
                f"**{fmt_frac(picos.get('n_tmax_40'), n_mun)}** ≥ 40 °C · "
                f"**{fmt_frac(picos.get('n_tmax_37'), n_mun)}** ≥ 37 °C.",
                f"- **Contexto da grade do dia (rodada):** Tmáx máx. **{fmt_num(tmax_max, 1, ' °C')}** "
                f"em {ext.get('municipio') or '—'} · **{fmt_frac(n_tmax, n)}** ≥ 37 °C hoje · "
                f"persistência P95≥2d em **{fmt_frac(n_onda, n)}** — distinto do EHF (≥ 3 dias).",
            ]
        )
        ranking = picos.get("ranking_40") or picos.get("ranking_41") or picos.get("ranking_37") or []
        if ranking:
            rows = [
                [
                    str(r.get("municipio") or "—"),
                    fmt_num(r.get("tmax_max"), 1, " °C"),
                    str(r.get("data_pico") or "—"),
                ]
                for r in ranking[:12]
            ]
            linhas.extend(
                [
                    "",
                    "**Picos de Tmáx municipal na janela (≥ 40 °C quando houver; senão ≥ 37 °C)**",
                    "",
                    md_table(["Município", "Tmáx pico", "Data"], rows),
                    "",
                    "Fonte: histórico municipal diário ARARAS (grade Open-Meteo). Pico = máxima diária por município na janela.",
                ]
            )
        if maps.get("grafico_picos_tmax"):
            linhas.extend(
                [
                    "",
                    figs.caption("Ranking de picos de Tmáx na janela"),
                    "",
                    f"![Picos de Tmáx]({maps.get('grafico_picos_tmax')})",
                    "",
                    "Fonte: ARARAS MT — histórico municipal diário da janela (observado).",
                ]
            )
    else:
        linhas.append(
            f"- **Calor na rodada (grade ARARAS):** Tmáx máx. estadual **{fmt_num(tmax_max, 1, ' °C')}** · "
            f"**{fmt_frac(n_tmax, n)}** ≥ 37 °C · persistência P95≥2d em **{fmt_frac(n_onda, n)}**."
        )
    cui_tmax = cui_g.get("tmax_max") if cui_g.get("tmax_max") is not None else om_cui
    cui_data = cui_g.get("data_pico")
    if cui_tmax is not None:
        cui_txt = (
            f"- **Cuiabá (grade Open-Meteo):** pico na janela **{fmt_num(cui_tmax, 1, ' °C')}**"
            + (f" em {cui_data}." if cui_data else ".")
        )
    else:
        cui_txt = "- **Cuiabá (grade Open-Meteo):** sem pico de grade disponível nesta janela."
    linhas.extend(
        [
            cui_txt,
            f"- **Vermelho/roxo:** **{fmt_frac(snap.get('n_vermelha_roxa'), n)}** agora · "
            f"projeção ~7d **{fmt_frac(int((snap.get('niveis_projecao_7d') or {}).get('vermelha') or 0) + int((snap.get('niveis_projecao_7d') or {}).get('roxa') or 0), n)}**.",
            "",
            "Fonte: ARARAS MT/CIEVS-MT; Open-Meteo Archive (grade). "
            "Séries longas (Cuiabá e Tmáx mensal estadual): **anexo técnico**.",
        ]
    )

    anexo: list[str] = ["", "### Séries climáticas de suporte (anexo técnico)", ""]
    if maps.get("serie_cuiaba_temps"):
        ini = maps.get("serie_cuiaba_inicio") or "—"
        fim = maps.get("serie_cuiaba_fim") or "—"
        anexo.extend(
            [
                figs.caption(
                    f"Temperaturas diárias em Cuiabá ({ini[:4] if len(str(ini)) >= 4 else ini}–"
                    f"{fim[:4] if len(str(fim)) >= 4 else fim}) — observado"
                ),
                "",
                f"![Temperaturas diárias Cuiabá]({maps.get('serie_cuiaba_temps')})",
                "",
                f"Fonte: Open-Meteo Archive (ponto Cuiabá). Período observado {ini} a {fim}.",
                "",
            ]
        )
    if maps.get("serie_cuiaba_amplitude"):
        anexo.extend(
            [
                figs.caption("Amplitude térmica diária em Cuiabá — observado"),
                "",
                f"![Amplitude térmica Cuiabá]({maps.get('serie_cuiaba_amplitude')})",
                "",
                "Fonte: Open-Meteo Archive (máxima − mínima diária) com média móvel de 30 dias. Série observada.",
                "",
            ]
        )
    if maps.get("serie_climatica"):
        ini = maps.get("serie_climatica_inicio") or "—"
        fim = maps.get("serie_climatica_fim") or "—"
        anexo.extend(
            [
                figs.caption(
                    f"Série climática operacional estadual (Tmáx mensal, {ini} a {fim}) — observado"
                ),
                "",
                f"![Série climática Tmáx]({maps.get('serie_climatica')})",
                "",
                f"Fonte: grade operacional ARARAS MT. Período observado {ini} a {fim}.",
                "",
            ]
        )
    anexo_md = "\n".join(anexo) if len(anexo) > 4 else ""
    return "\n".join(linhas), anexo_md


def _cards_executivos(snap: dict[str, Any]) -> str:
    """Seis cartões do resumo — substitui a tabela operacional da primeira página."""
    if not snap.get("disponivel"):
        return INDISPONIVEL
    n = snap.get("n_municipios")
    crit = snap.get("n_vermelha_roxa")
    proj = snap.get("niveis_projecao_7d") or {}
    proj_crit = int(proj.get("vermelha") or 0) + int(proj.get("roxa") or 0)
    picos = snap.get("picos_termicos") or {}
    ext = (snap.get("extremos") or {}).get("tmax") or {}
    pico = picos.get("tmax_max_semana") if picos.get("ok") else None
    n41 = picos.get("n_tmax_41") if picos.get("ok") else None
    n40 = picos.get("n_tmax_40") if picos.get("ok") else None
    n37_sem = picos.get("n_tmax_37") if picos.get("ok") else None
    pct = ""
    if crit is not None and n:
        pct = f"{fmt_num(100.0 * float(crit) / float(n), 1, '%')} do estado"
    if pico is not None:
        calor_max = f"pico semana **{fmt_num(pico, 1, ' °C')}**"
        calor_cnt = (
            f"**{fmt_int(n41)}** ≥ 41 °C · **{fmt_int(n40)}** ≥ 40 °C · "
            f"**{fmt_frac(n37_sem, n)}** ≥ 37 °C (janela)"
        )
    else:
        calor_max = f"máxima **{fmt_num(ext.get('tmax'), 1, ' °C')}**"
        calor_cnt = f"**{fmt_frac(snap.get('n_tmax_37'), n)}** ≥ 37 °C"
    return f"""| RISCO ATUAL | PROJEÇÃO ~7 DIAS | CALOR |
| --- | --- | --- |
| **{fmt_int(crit)}/{fmt_int(n)}** vermelho ou roxo | **{fmt_int(proj_crit)}/{fmt_int(n)}** vermelho ou roxo | {calor_max} |
| {pct} | agravamento disseminado | {calor_cnt} |

| UMIDADE | FOGO | QUALIDADE DO AR |
| --- | --- | --- |
| **{fmt_frac(snap.get('n_umidade_30'), n)}** ≤ 30% | **{fmt_int(snap.get('focos_7d_total'))}** focos de calor | **{fmt_frac(snap.get('n_pm25_25'), n)}** ≥ 25 µg/m³ |
| mediana {fmt_num(snap.get('umidade_mediana'), 0, '%')} | Satélite de referência do Programa Queimadas · 7 dias · {fmt_int(snap.get('n_com_focos_7d'))} municípios · {fmt_int(snap.get('deteccoes_7d_total'))} detecções multi-satélite | máximo {fmt_num(snap.get('pm25_max'), 1, ' µg/m³')} |

{(snap.get('rit') or {}).get('card_md') or ''}
"""


def _fonte_araras(semana: dict[str, Any], sufixo: str = "") -> str:
    when = semana.get("gerado_em_pt") or semana.get("gerado_em") or "—"
    base = f"ARARAS MT/CIEVS-MT, rodada de {when}"
    return f"{base}. {sufixo}".strip() if sufixo else f"{base}."


def _n_classe(snap: dict[str, Any], chave: str, alt: Any = None) -> str:
    if snap.get("n_municipios") is None:
        return INDISPONIVEL
    niveis = snap.get("niveis") or {}
    v = niveis.get(chave)
    if v is None:
        v = alt
    return fmt_int(0 if v is None else v)


def _leitura_executiva(snap: dict[str, Any]) -> str:
    niveis = snap.get("niveis") or {}
    n = snap.get("n_municipios")
    crit = snap.get("n_vermelha_roxa")
    proj = snap.get("niveis_projecao_7d") or {}
    proj_crit = int(proj.get("vermelha") or 0) + int(proj.get("roxa") or 0)
    n37 = int(snap.get("n_tmax_37") or 0)
    n25 = int(snap.get("n_pm25_25") or 0)
    chuva_ok = bool(snap.get("impacto_chuva_ok")) or bool((snap.get("impacto_chuva") or {}).get("ok"))
    linhas = [
        f"**Situação:** {fmt_frac(crit, n)} em vermelho/roxo ({fmt_distribuicao_niveis(niveis)}).",
        f"**Projeção ~7 dias:** {fmt_frac(proj_crit, n)} em vermelho/roxo — agravamento disseminado.",
        "**Drivers da escalada (modelo):** Tmáx prevista, UTCI, risco cumulativo e onda P95 "
        "(persistência térmica projetada) — **não** o EHF.",
        "**EHF/GeoCalor não entra no cálculo da classe projetada**; é monitoramento observado separado.",
        "**RIT (Risco Integrado Territorial):** leitura observada multidomínio (máx. entre térmico, ar, hidro, EHF, pressão fresca e fragilidade de rede/IRM) — **paralelo** à projeção ~7d térmica; ver bloco na seção 4.",
    ]
    if n37:
        linhas.append(f"**Exposição térmica na rodada:** Tmáx ≥ 37 °C em {fmt_frac(n37, n)}.")
    linhas.append(
        f"**Qualidade do ar (contexto concomitante, não driver do modelo):** "
        f"PM2,5 ≥ 25 µg/m³ em {fmt_frac(n25, n)}"
        + (
            f" (máx. {fmt_num(snap.get('pm25_max'), 1, ' µg/m³')})."
            if snap.get("pm25_max") is not None
            else "."
        )
    )
    if chuva_ok:
        chuva_md = str(snap.get("impacto_chuva_md") or "").strip()
        if chuva_md:
            linhas.append("**Chuva na SE corrente:** ver bloco operacional de impacto hídrico (alívio temporário).")
    agr = snap.get("agravos_monitorados") or {}
    dw = agr.get("dw_epidemiologia") or {}
    esus = dw.get("esus_aps") or agr.get("esus_aps") or {}
    if esus.get("status") == "ativo" and int(esus.get("municipios") or 0) > 0:
        linhas.append(
            f"**Vulneráveis (e-SUS APS):** idosos 60+ **{fmt_int(esus.get('idoso_60mais'))}** · "
            f"gestantes **{fmt_int(esus.get('gestante'))}** · asma **{fmt_int(esus.get('asma'))}** · "
            f"**{fmt_int(esus.get('municipios_vermelho_roxo'))}** municípios vermelho/roxo com cadastro. "
            "Priorizar também povos indígenas e quilombolas nos territórios críticos."
        )
    else:
        linhas.append(
            "Priorizar preparação assistencial nos vermelhos/roxos, com atenção a povos indígenas, "
            "quilombolas, idosos, gestantes e trabalhadores expostos."
        )
    return " ".join(linhas)


def _implicacao_operacional(snap: dict[str, Any]) -> str:
    """Frase dinâmica conforme presença de calor, fumaça e baixa umidade na rodada."""
    n37 = int(snap.get("n_tmax_37") or 0)
    n25 = int(snap.get("n_pm25_25") or 0)
    n30 = int(snap.get("n_umidade_30") or 0)
    eixos: list[str] = []
    if n37 > 0:
        eixos.append("calor")
    if n25 > 0:
        eixos.append("fumaça/PM2,5")
    if n30 > 0:
        eixos.append("ar seco")
    nucleo = " + ".join(eixos) if eixos else "cenário operacional"
    return (
        f"**Implicação.** Manter vigilância e capacidade assistencial nos prioritários "
        f"({nucleo}). Manter prontidão na projeção ~7d e priorizar vulneráveis "
        f"(idosos, gestantes, asma, povos indígenas e quilombolas) nos vermelhos/roxos."
    )


def _leitura_regional_curta(snap: dict[str, Any]) -> str:
    """2–4 frases a partir da tabela de regionais — suprime se mapeamento indisponível."""
    regs = [
        r
        for r in (snap.get("regionais") or [])
        if str(r.get("regional") or "").strip() not in {"", "—", "nan", "None"}
    ]
    if not regs:
        return ""
    top = regs[0]
    nome_top = str(top.get("regional") or "—")
    n_vr = top.get("n_vermelha_roxa")
    tmax_top = max(regs, key=lambda r: float(r.get("tmax_mediana") or 0) if r.get("tmax_mediana") is not None else -1.0)
    import re as _re

    def _n_aumento(txt: Any) -> int:
        m = _re.search(r"↑\s*(\d+)", str(txt or ""))
        return int(m.group(1)) if m else 0

    up_top = max(regs, key=lambda r: _n_aumento(r.get("tendencia_7d")))
    frases = [
        f"**Leitura regional.** A maior concentração nas classes vermelha e roxa está em "
        f"**{nome_top}** ({fmt_plural(n_vr, 'município', 'municípios')})."
    ]
    if _n_aumento(up_top.get("tendencia_7d")) > 0:
        frases.append(
            f"O maior número de municípios em aumento de classe na projeção de sete dias "
            f"concentra-se em **{up_top.get('regional')}** "
            f"({_n_aumento(up_top.get('tendencia_7d'))} em elevação)."
        )
    if tmax_top.get("tmax_mediana") is not None:
        frases.append(
            f"A maior mediana regional de Tmáx no recorte é **{fmt_num(tmax_top.get('tmax_mediana'), 1, ' °C')}** "
            f"({tmax_top.get('regional')})."
        )
    return " ".join(frases)


def _frase_exposicao_rodada(snap: dict[str, Any]) -> str:
    n37 = int(snap.get("n_tmax_37") or 0)
    n25 = int(snap.get("n_pm25_25") or 0)
    n30 = int(snap.get("n_umidade_30") or 0)
    partes: list[str] = []
    if n37 > 0:
        partes.append("calor extremo")
    if n30 > 0:
        partes.append("ar seco")
    if n25 > 0:
        partes.append("fumaça")
    if not partes:
        return "Há exposição climática operacionalmente relevante em frações do estado;"
    if len(partes) == 1:
        return f"Há {partes[0]} em frações relevantes do estado;"
    if len(partes) == 2:
        return f"Há {partes[0]} e {partes[1]} em frações relevantes do estado;"
    return f"Há {partes[0]}, {partes[1]} e {partes[2]} em frações relevantes do estado;"


def _prioridades_imediatas() -> str:
    return (
        "- Vigilância de agravos por calor/fumaça nos vermelhos/roxos.\n"
        "- Capacidade assistencial e insumos onde Tmáx ≥ 37 °C ou PM2,5 ≥ 25 µg/m³.\n"
        "- Articular regionais, DSEI/SESAI e Saúde do Trabalhador nos prioritários.\n"
        "- Priorizar APS e vulneráveis (idosos 60+, gestantes, asma, povos indígenas e quilombolas) "
        "nos municípios vermelho/roxo; manter prontidão na projeção ~7d."
    )


def _destaques_executivos(snap: dict[str, Any]) -> str:
    if not snap.get("disponivel"):
        return ""
    n = snap.get("n_municipios")
    crit = snap.get("n_vermelha_roxa")
    n25 = snap.get("n_pm25_25")
    focos = snap.get("focos_7d_total")
    ext = (snap.get("extremos") or {}).get("tmax") or {}
    proj = snap.get("niveis_projecao_7d") or {}
    proj_crit = int(proj.get("vermelha") or 0) + int(proj.get("roxa") or 0)
    linhas = [
        f"- **{fmt_frac(crit, n)}** — municípios nas classes vermelha ou roxa.",
        f"- **{fmt_num(ext.get('tmax'), 1, ' °C')}** — maior Tmáx municipal ({ext.get('municipio') or '—'}).",
        f"- **{fmt_int(focos)} focos no {FOGO_SATELITE_REFERENCIA_CURTO}** — acumulado de sete dias"
        + (
            f"; {fmt_int(snap.get('deteccoes_7d_total'))} detecções multi-satélite no mesmo período."
            if snap.get("deteccoes_7d_total") is not None
            else "."
        ),
        f"- **{fmt_frac(n25, n)}** — municípios com PM2,5 ≥ 25 µg/m³.",
        f"- **{fmt_int(proj_crit)} municípios** — permanecem nas classes vermelha ou roxa na projeção de sete dias.",
    ]
    return "**Destaques da rodada**\n\n" + "\n".join(linhas)


def _painel_semaforo(snap: dict[str, Any], cenario: dict[str, Any]) -> str:
    enso = cenario.get("enso") or {}
    n = snap.get("n_municipios")
    n_crit = snap.get("n_vermelha_roxa")
    n25 = snap.get("n_pm25_25")
    cob_hidro = snap.get("cobertura_hidro")
    tend7 = snap.get("tendencia_7d") or {}
    delta = snap.get("delta_projecao") or {}
    n_d = snap.get("delta_n_comparavel") or n
    n_est = int(delta.get("estabilidade") or 0)
    n_melhora = int(delta.get("melhora") or 0)
    n_up = int(delta.get("aumento_1") or 0) + int(delta.get("aumento_2plus") or 0)
    proj = snap.get("niveis_projecao_7d") or {}
    proj_crit = int(proj.get("vermelha") or 0) + int(proj.get("roxa") or 0)

    def _tend_vocab(chave: str) -> str:
        if chave == "enso":
            return "persistência"
        # Fogo e qualidade do ar: sem modelo de previsão específico nesta versão
        if chave in {"fogo", "ar"}:
            return "não calculada"
        if not delta and chave != "enso":
            return "tendência não calculável"
        if chave in {"calor", "risco", "risco_termico"}:
            # Risco térmico / integrado projetado
            if n_up > 0 and n_d and n_up >= max(1, int(n_d * 0.3)):
                return "agravamento disseminado"
            if n_up > 0:
                return "agravamento localizado"
            if n_melhora > n_up and n_melhora > 0:
                return "melhora"
            if n_est >= (n_d or 0) * 0.7 and (n_crit or 0) > (n or 1) * 0.4:
                return "estabilidade em patamar elevado"
            return "persistência"
        return "tendência não calculável"

    if not snap.get("disponivel"):
        rows = [["El Niño", SELIND, "—", "—", INDISPONIVEL]]
    else:
        situ_ar = (
            f"Atenção localizada — {fmt_frac(n25, n)} municípios ≥ 25 µg/m³"
            if n25 is not None
            else INDISPONIVEL
        )
        situ_hidro = (
            "Sinais heterogêneos no recorte disponível"
            if cob_hidro and n and cob_hidro < n
            else (fmt_counts(snap.get("hidro") or {}) if snap.get("hidro") else INDISPONIVEL)
        )
        cob_hidro_txt = fmt_frac(cob_hidro, n) if cob_hidro is not None else INDISPONIVEL
        n_com_focos = snap.get("n_com_focos_7d")
        cob_focos = snap.get("cobertura_focos")
        ff = snap.get("fire_facts") or {}
        so_det = bool(ff.get("coverage_is_detection"))
        if so_det or (
            cob_focos is not None and n_com_focos is not None and n and int(cob_focos) == int(n_com_focos) and int(cob_focos) < int(n)
        ):
            cob_fogo_txt = f"registro {fmt_frac(cob_focos, n)}"
            situ_fogo = (
                f"Focos em {fmt_int(n_com_focos)} de {fmt_int(n)} municípios"
                if n_com_focos is not None and n
                else INDISPONIVEL
            )
        else:
            cob_fogo_txt = fmt_frac(cob_focos, n) if cob_focos is not None else INDISPONIVEL
            situ_fogo = (
                f"Focos detectados em {fmt_int(n_com_focos)} de {fmt_int(n)} municípios"
                if n_com_focos is not None and n
                else INDISPONIVEL
            )
        rows = [
            [
                "El Niño",
                "Ativo" if "niño" in str(enso.get("status", "")).lower() else "Inativo",
                _tend_vocab("enso"),
                "—",
                str(enso.get("intensidade") or INDISPONIVEL),
            ],
            [
                "Calor / risco térmico projetado",
                "Atenção elevada" if n_crit and n and n_crit > n * 0.4 else "Atenção moderada",
                _tend_vocab("calor"),
                fmt_frac(snap.get("cobertura_tmax"), n),
                _leitura_faixa(
                    snap.get("tmax_mediana"),
                    snap.get("tmax_min"),
                    snap.get("tmax_max"),
                    casas=1,
                    suf=" °C",
                    n_ext=snap.get("n_tmax_37"),
                    n=n,
                    criterio="com Tmáx ≥ 37 °C",
                ),
            ],
            [
                "Umidade",
                "Atenção" if (snap.get("n_umidade_30") or 0) > 0 else "Sem alerta operacional",
                "não calculada",
                fmt_frac(snap.get("cobertura_umidade"), n),
                _leitura_faixa(
                    snap.get("umidade_mediana"),
                    snap.get("umidade_min"),
                    snap.get("umidade_max"),
                    casas=0,
                    suf="%",
                    n_ext=snap.get("n_umidade_30"),
                    n=n,
                    criterio="com UR ≤ 30%",
                ),
            ],
            [
                "Fogo",
                situ_fogo,
                _tend_vocab("fogo"),
                cob_fogo_txt,
                f"{fmt_int(snap.get('focos_7d_total'))} focos no {FOGO_SATELITE_REFERENCIA_CURTO} (7 dias)"
                + (
                    f"; {fmt_int(snap.get('deteccoes_7d_total'))} detecções multi-satélite"
                    if snap.get("deteccoes_7d_total") is not None
                    else ""
                ),
            ],
            [
                "Qualidade do ar",
                situ_ar,
                _tend_vocab("ar"),
                fmt_frac(snap.get("cobertura_pm25") or snap.get("cobertura_tmax"), n),
                _leitura_faixa(
                    snap.get("pm25_mediana"),
                    snap.get("pm25_min"),
                    snap.get("pm25_max"),
                    casas=1,
                    suf=" µg/m³",
                    n_ext=snap.get("n_pm25_25"),
                    n=n,
                    criterio="≥ 25 µg/m³",
                ),
            ],
            [
                "Recursos hídricos",
                situ_hidro,
                "não calculada",
                cob_hidro_txt,
                "Interpretação limitada pela cobertura parcial."
                if cob_hidro and n and cob_hidro < n
                else fmt_counts(snap.get("hidro") or {}),
            ],
            [
                "Risco integrado projetado (~7 dias)",
                fmt_frac(n_crit, n),
                _tend_vocab("risco"),
                fmt_frac(n, n) if n else "—",
                (
                    f"Projeção: {fmt_frac(proj_crit, n)} nas classes vermelha ou roxa"
                    if proj_crit and n
                    else "Classes vermelha ou roxa no território estadual"
                ),
            ],
        ]
    tabela = md_table(
        ["Dimensão", "Situação atual", "Tendência ~7 dias", "Cobertura", "Leitura"],
        rows,
    )
    return (
        tabela
        + "\n\n_Nota: referências operacionais — Painel El Niño/NOAA; Tmáx e UR municipais "
        "(mediana, mínimo, máximo e municípios no extremo de atenção); "
        "focos INPE (7 dias); PM2,5; situação hidrológica municipal; classificação ARARAS._"
    )


def _mapa_sintese(snap: dict[str, Any]) -> str:
    if not snap.get("disponivel"):
        return INDISPONIVEL
    atual = snap.get("niveis") or {}
    proj = snap.get("niveis_projecao_7d") or {}
    delta = snap.get("delta_projecao") or {}

    def _linhas(d: dict[str, int]) -> str:
        return fmt_distribuicao_niveis(d)

    mudanca = ""
    if delta:
        from sisclima.engines.boletim_el_nino.formatters import fmt_plural

        mudanca = (
            f"- Aumento de 2+ níveis: {fmt_plural(delta.get('aumento_2plus', 0), 'município', 'municípios')}\n"
            f"- Aumento de 1 nível: {fmt_plural(delta.get('aumento_1', 0), 'município', 'municípios')}\n"
            f"- Estabilidade: {fmt_plural(delta.get('estabilidade', 0), 'município', 'municípios')}\n"
            f"- Melhora: {fmt_plural(delta.get('melhora', 0), 'município', 'municípios')}"
        )
    else:
        mudanca = NAO_CALCULADO

    return f"""**Atual:** {_linhas(atual)}. `{SELOBS}`

**Projeção ~7 dias:** {_linhas(proj)}. `{SELPROJ}`

**Mudança esperada**
{mudanca}"""


def _label_nivel(k: str) -> str:
    return {"amarela": "Amarelo", "laranja": "Laranja", "vermelha": "Vermelho", "roxa": "Roxo"}.get(k, k)


def _bloco_ocupacao_sisreg_md(*, publico: bool = False) -> str:
    """Caixa operacional IndicaSUS (SIEGES) × SISREG para o §11.2b."""
    try:
        from sisclima.reporting.quadro_risco_pressao import quadro_risco_pressao

        q = quadro_risco_pressao()
    except Exception:
        q = {"disponivel": False}
    if not q.get("disponivel"):
        return (
            "Dois sinais distintos na operação CIEVS: **ocupação hospitalar (IndicaSUS)** e "
            "**pressão hospitalar (SISREG)**. Dados da rodada indisponíveis neste momento."
        )

    linhas = [
        "Dois sinais distintos na operação CIEVS:",
        "",
        "| Conceito | Fonte | Interpretação |",
        "|---|---|---|",
        "| **Ocupação hospitalar** | IndicaSUS / BdSES (filtros SIEGES) | % de leitos ocupados — só municípios com leitos elegíveis |",
        "| **Pressão hospitalar / regulação** | SISREG | Fila e solicitações — demanda territorial (com ou sem hospital próprio) |",
        "",
        "**Rodada atual (ocupação ponderada por leitos)**",
        "",
        f"- Ocupação estadual: **{q.get('ocupacao_ponderada_txt') or q.get('ocupacao_media_txt') or '—'}%** "
        f"({q.get('leitos_ocupados_txt') or '—'} ocupados / {q.get('leitos_total_txt') or '—'} elegíveis)",
        f"- Cobertura: **{q.get('ocupacao_n_tempo_real') or '—'}** municípios com taxa · "
        f"**{q.get('ocupacao_n_sem_leitos') or '—'}** sem leitos elegíveis no recorte"
        + (f" · {q.get('unidades_n')} unidades" if q.get("unidades_n") else ""),
        f"- Pressão SISREG (solicitações no recorte da rodada): **{q.get('sisreg_n') or '—'}** municípios · "
        f"média municipal {q.get('sisreg_solicitacoes_media_txt') or '—'} · "
        f"máximo municipal {q.get('sisreg_solicitacoes_max_txt') or '—'} "
        "(métrica de fila/demanda regulada — temporalidade conforme carga da Sala).",
        "- Ocupação calculada segundo filtros assistenciais institucionais do SIEGES/IndicaSUS "
        "(detalhamento técnico no painel/anexo).",
        "",
        f"_{q.get('nota_separacao')}_",
    ]

    por_reg = [
        r
        for r in (q.get("ocupacao_por_regional") or [])
        if str(r.get("regional") or "").strip() not in {"", "—", "nan", "None"}
    ]
    if por_reg:
        rows_reg = []
        for r in por_reg:
            oc = r.get("ocupacao_ponderada")
            lt = r.get("leitos_total")
            lo = r.get("leitos_ocupados")
            rows_reg.append(
                [
                    str(r.get("regional") or "—"),
                    f"{oc:.1f}%".replace(".", ",") if oc is not None else "—",
                    (
                        f"{int(lo)}/{int(lt)}"
                        if lo is not None and lt is not None
                        else "—"
                    ),
                    str(int(r.get("n_com_taxa") or 0)),
                    str(int(r.get("n_sem_leitos") or 0)),
                    str(int(r.get("n_municipios") or 0)),
                ]
            )
        linhas.extend(
            [
                "",
                "**Ocupação IndicaSUS por regional de saúde**",
                "",
                md_table(
                    [
                        "Regional",
                        "Ocup. ponderada",
                        "Leitos ocup./elegíveis",
                        "Mun. c/ taxa",
                        "Sem leitos",
                        "Total mun.",
                    ],
                    rows_reg,
                ),
                "",
                "_Termômetro assistencial: % ponderado por leitos elegíveis (SIEGES). "
                "Municípios sem leitos no recorte não entram no denominador do %._",
            ]
        )
    else:
        linhas.extend(
            [
                "",
                "**Síntese estadual da ocupação hospitalar**",
                "",
                "Distribuição por Regional de Saúde indisponível nesta rodada "
                "(mapeamento municipal→regional ausente). Mantém-se a síntese estadual acima.",
            ]
        )

    top_oc = q.get("top_ocupacao") or []
    if top_oc:
        rows = []
        for r in top_oc:
            oc = r.get("ocupacao_leitos_pct")
            sis = r.get("kpi_sisreg_solicitacoes")
            rows.append(
                [
                    str(r.get("municipio") or "—"),
                    f"{oc:.1f}%".replace(".", ",") if oc is not None else "—",
                    f"{sis:.0f}" if sis is not None else "—",
                ]
            )
        linhas.extend(
            [
                "",
                "**Municípios com maior ocupação IndicaSUS**",
                "",
                md_table(["Município", "Ocup. IndicaSUS", "SISREG sol."], rows),
            ]
        )

    # Anexo Sala: sem IndicaSUS × alta pressão SISREG (omitir em versão pública)
    top_sem = q.get("top_sem_leitos_sisreg") or []
    if top_sem and not publico:
        rows = []
        for r in top_sem:
            sis = r.get("kpi_sisreg_solicitacoes")
            reg = r.get("regional")
            if reg is None or str(reg).strip().lower() in {"", "nan", "none", "null"}:
                reg = "—"
            rows.append(
                [
                    str(r.get("municipio") or "—"),
                    str(reg),
                    f"{sis:.0f}" if sis is not None else "—",
                ]
            )
        linhas.extend(
            [
                "",
                "**Sem leitos elegíveis IndicaSUS — maior pressão SISREG (Sala)**",
                "",
                md_table(["Município", "Regional", "SISREG sol."], rows),
            ]
        )

    return "\n".join(linhas)


def _bloco_atos_oficiais(snap: dict[str, Any] | None = None) -> str:
    try:
        from sisclima.reporting.decretos_alerta import bloco_decretos_markdown_boletim

        # Busca já pode ter sido feita no builder; aqui só monta o markdown a partir da base.
        _ = snap
        return bloco_decretos_markdown_boletim(max_iomat=5, atualizar=False)
    except Exception as exc:  # noqa: BLE001
        return (
            "### Atos oficiais correlatos (decretos e portarias)\n\n"
            f"_Indisponível nesta rodada ({exc})._\n"
        )


def format_markdown(
    cenario: dict[str, Any],
    semana: dict[str, Any],
    snap: dict[str, Any],
    *,
    alertas: dict[str, Any] | None = None,
    inmet: dict[str, Any] | None = None,
    estoque_saf: dict[str, Any] | None = None,
    maps: dict[str, Any] | None = None,
    prontidao: dict[str, Any] | None = None,
    territorios: dict[str, Any] | None = None,
    referencias: list[str] | None = None,
    publico: bool = False,
) -> str:
    enso = cenario.get("enso") or {}
    mt = cenario.get("mato_grosso") or {}
    br = cenario.get("brasil_aso") or {}
    ext = snap.get("extremos") or {}
    recs = cenario.get("recomendacoes_estados") or []
    agr = snap.get("agravos_monitorados") or {}
    med = snap.get("medidor_trajetoria") or {}
    inmet = alertas or inmet or {}
    estoque_saf = estoque_saf or {}
    maps = maps or {}
    prontidao = prontidao or {}
    territorios = territorios or {}
    refs_biblio = referencias or REFERENCIAS_PADRAO
    cite_painel = cite("painel_el_nino_02")

    if USAR_TITULO_SALA_SITUACAO:
        titulo = TITULO_SALA_SITUACAO
    elif publico:
        titulo = "Relatório semanal El Niño — ARARAS MT"
    else:
        titulo = TITULO_PRODUTO_ATUAL
    secao_mun = (
        "Municípios prioritários para acompanhamento"
        if publico
        else "Municípios prioritários para resposta e preparação"
    )

    n_mun_txt = fmt_int(snap.get("n_municipios")) if snap.get("disponivel") else INDISPONIVEL
    raw_ref = snap.get("data_referencia") or "rodada atual"
    ref_data = fmt_date_pt(raw_ref) if raw_ref not in {"rodada atual", None} else str(raw_ref)

    linhas_top: list[list[str]] = []
    for p in (snap.get("prioritarios") or [])[:10]:
        atual = str(p.get("nivel") or "—").title()
        proj = str(p.get("nivel_predicao_7d") or "—").title()
        exp = str(p.get("exposicao_principal") or p.get("determinante") or "calor, fumaça ou fogo")
        linhas_top.append(
            [
                str(p.get("municipio") or "—"),
                f"{atual} → {proj}",
                exp,
                "Preparação assistencial e vigilância",
            ]
        )
    tab_prior = md_table(
        ["Município", "Atual → ~7 dias", "Principal exposição", "Prioridade de preparação"],
        linhas_top if snap.get("disponivel") else [],
    )

    linhas_reg: list[list[str]] = []
    for r in (snap.get("regionais") or [])[:8]:
        nome_reg = str(r.get("regional") or "").strip()
        if nome_reg in {"", "—", "nan", "None"}:
            continue
        linhas_reg.append(
            [
                nome_reg,
                fmt_int(r.get("n_vermelha_roxa")),
                str(r.get("tendencia_7d") or "—"),
                fmt_num(r.get("tmax_mediana"), 1, " °C"),
            ]
        )
    if linhas_reg and snap.get("disponivel"):
        tab_reg = bloco_tabela(
            "Regionais de saúde com maior concentração de municípios nas classes vermelha e roxa",
            md_table(
                ["Regional", "Municípios em vermelho/roxo (atual)", "Mudança ~7 dias", "Tmáx mediana"],
                linhas_reg,
            ),
            "ARARAS MT/CIEVS-MT, classificação municipal agregada por regional de saúde.",
            nota=(
                "↑ indica aumento da classificação; → estabilidade; ↓ redução, "
                "considerando todos os municípios da Regional."
            ),
        )
        secao_reg = f"### 11.1 Regionais de Saúde\n\n{tab_reg}\n\n{_leitura_regional_curta(snap)}\n"
    else:
        tab_reg = ""
        secao_reg = ""  # REGIONAL_SECTION_SUPPRESSED
    fonte_rodada = _fonte_araras(semana)
    bloco_ocup_sisreg = _bloco_ocupacao_sisreg_md(publico=publico)
    tab_ind = bloco_tabela(
        "Indicadores da rodada e municípios em atenção",
        md_table(
            ["Indicador", "Situação da rodada", "Municípios em atenção"],
            [
                [
                    "Temperatura",
                    f"mediana {fmt_num(snap.get('tmax_mediana'), 1, ' °C')} · máximo {fmt_num(snap.get('tmax_max'), 1, ' °C')}",
                    f"{fmt_frac(snap.get('n_tmax_37'), snap.get('n_municipios'))} ≥ 37 °C",
                ],
                [
                    "Umidade",
                    f"mediana {fmt_num(snap.get('umidade_mediana'), 0, '%')} · mínimo {fmt_num(snap.get('umidade_min'), 0, '%')}",
                    f"{fmt_frac(snap.get('n_umidade_30'), snap.get('n_municipios'))} ≤ 30%",
                ],
                [
                    "PM2,5",
                    f"mediana {fmt_num(snap.get('pm25_mediana'), 1, ' µg/m³')} · máximo {fmt_num(snap.get('pm25_max'), 1, ' µg/m³')}",
                    f"{fmt_frac(snap.get('n_pm25_25'), snap.get('n_municipios'))} ≥ 25 µg/m³",
                ],
                [
                    "*Universal Thermal Climate Index* (UTCI)",
                    f"mediana {fmt_num(snap.get('utci_mediana'), 1, ' °C')}",
                    f"{fmt_frac(snap.get('n_utci_32'), snap.get('n_municipios'))} ≥ 32 °C",
                ],
            ],
        ),
        fonte_rodada,
    )
    pront_tab = prontidao.get("tabela_md", INDISPONIVEL)
    if prontidao.get("validado", True) and str(pront_tab).startswith("|"):
        pront_tab = bloco_tabela(
            "Índice de prioridade de preparação clima–saúde (dez municípios)",
            pront_tab,
            fonte_rodada,
        )
    elif not prontidao.get("validado", True):
        pront_tab = (
            "_Índice de prioridade de preparação não publicado nesta rodada: "
            "inconsistência ou saturação detectada._"
        )
    tab_impactos = impactos_potenciais_saude(snap=snap)
    if str(tab_impactos).startswith("|"):
        # nota hidrológica pode vir após a tabela
        partes = tab_impactos.split("\n\n>", 1)
        tab_impactos = bloco_tabela(
            "Impactos potenciais à saúde segundo cenário de exposição",
            partes[0].strip(),
            fonte_rodada,
        )
        if len(partes) > 1:
            tab_impactos += "\n\n>" + partes[1]

    eta_txt = NAO_CALCULADO
    if med and med.get("disponivel"):
        eta_dias = med.get("eta_critico_dias")
        if eta_dias is None:
            eta_txt = "Não estimável com o saldo atual de tendência"
        else:
            eta_txt = f"{fmt_int(round(float(eta_dias)))} dias (~{fmt_num(float(eta_dias) / 7.0, 1)} semanas)"

    mapa_md = ""
    if maps.get("disponivel"):
        dc = maps.get("delta_counts") or snap.get("delta_projecao") or {}
        n_delta = maps.get("delta_n") or snap.get("delta_n_comparavel") or snap.get("n_municipios")
        sem_par = snap.get("delta_sem_pareamento") or 0
        interp_delta = interpretar_tendencia(snap)
        if (dc.get("aumento_1") or 0) == 0 and (dc.get("aumento_2plus") or 0) == 0:
            interp_delta += (
                f" A projeção indica predomínio de estabilidade territorial, com {fmt_int(dc.get('estabilidade'))} "
                f"municípios sem mudança de classe e {fmt_int(dc.get('melhora'))} apresentando melhora. "
                "Não foram identificados municípios com aumento de classificação na rodada analisada."
            )
        mapa_md = f"""
## 6. Mapa atual × mapa ~7 dias

**Mapa 1 – Classificação integrada de risco em Mato Grosso, {semana.get('periodo_pt', '')} (atual e ~7 dias)**

![Mapa 1]({maps.get('mapa_atual_projecao')})

Fonte: ARARAS MT/CIEVS-MT, rodada de {semana.get('gerado_em_pt', semana.get('gerado_em'))}.
Nota: as duas faces usam a mesma escala de classes (verde a roxo) para comparação visual direta.

**Atual.** {fmt_frac(snap.get('n_vermelha_roxa'), snap.get('n_municipios'))} vermelho ou roxo.  
**Projeção.** {fmt_frac(int((snap.get('niveis_projecao_7d') or {}).get('vermelha') or 0) + int((snap.get('niveis_projecao_7d') or {}).get('roxa') or 0), snap.get('n_municipios'))} vermelho ou roxo.  
**Agravamento.** {fmt_frac(snap.get('n_agravadores'), snap.get('delta_n_comparavel'))} sobem de classe.

**Mapa 2 – Variação projetada da classificação de risco em aproximadamente sete dias**

![Mapa 2]({maps.get('mapa_delta')})

Fonte: ARARAS MT/CIEVS-MT, rodada de {semana.get('gerado_em_pt', semana.get('gerado_em'))}.
Municípios com dados comparáveis: {fmt_frac(n_delta, snap.get('n_municipios'))}.
- Melhora: {fmt_frac(dc.get('melhora'), n_delta)}
- Estabilidade: {fmt_frac(dc.get('estabilidade'), n_delta)}
- Aumento de 1 nível: {fmt_frac(dc.get('aumento_1'), n_delta)}
- Aumento de 2 ou mais níveis: {fmt_frac(dc.get('aumento_2plus'), n_delta)}
{f"- Sem pareamento válido: {fmt_pareamento(sem_par, snap.get('n_municipios'))}" if sem_par else ""}

{snap.get("determinantes_projecao_md") or ""}

{_mapa_sintese(snap)}
"""
    else:
        mapa_md = f"_{maps.get('motivo', INDISPONIVEL)}_"

    fig_classes = ""
    figs = _FigCounter()
    fig_sazonalidade = ""
    if maps.get("grafico_sazonalidade_historico"):
        fonte_corr = maps.get("sazonalidade_fonte_corr") or "lags"
        nota_corr = (
            "lags clima→desfecho (Pearson R e Spearman ρ)"
            if fonte_corr == "lags"
            else "correlações ecológicas municipais nos top pares OR (Pearson R e Spearman ρ); lags temporais indisponíveis nesta rodada"
        )
        fig_sazonalidade = (
            f"{figs.caption('Sazonalidade operacional — histórico × atual e correlações (R e ρ)')}\n\n"
            f"![Sazonalidade histórico × atual]({maps.get('grafico_sazonalidade_historico')})\n\n"
            f"Fonte: ARARAS MT — índice sazonal mensal e {nota_corr}. "
            "Análise ecológica exploratória; não prova causalidade individual. "
            "* indica p<0,05 no painel de correlações.\n"
        )
    if maps.get("grafico_classes"):
        fig_classes = (
            f"![Classes ARARAS]({maps.get('grafico_classes')})\n\n"
            "Fonte: ARARAS MT/CIEVS-MT — contagem municipal por classe na rodada."
        )
    fig_esus = ""
    if maps.get("grafico_esus_vulneraveis"):
        fig_esus = (
            f"{figs.caption('Vulneráveis na APS por classe ARARAS')}\n\n"
            f"![Vulneráveis APS]({maps.get('grafico_esus_vulneraveis')})\n\n"
            "Fonte: e-SUS APS (cadastro) × classe ARARAS da rodada. Status: contexto/DEFASADO se carga atrasada."
        )
    secao_ondas_md, anexo_series_md = _secao_ondas_calor(snap, maps, figs)
    if maps.get("mapa_territorios"):
        fig_mapa3_extra = (
            "**Mapa 3 – Classificação de risco climático, aldeias indígenas e municípios com "
            "comunidades quilombolas certificadas em Mato Grosso**\n\n"
            f"![Mapa 3]({maps.get('mapa_territorios')})\n\n"
            f"Fonte: ARARAS MT/CIEVS-MT, com dados da Fundação Nacional dos Povos Indígenas (FUNAI) e "
            f"Fundação Cultural Palmares. Rodada de {semana.get('gerado_em_pt', '—')}.\n"
            "Nota: Aldeias são representadas por coordenadas georreferenciadas disponíveis. "
            "Para comunidades quilombolas sem coordenadas oficiais validadas, a representação indica "
            "presença municipal e não localização exata."
        )
    else:
        fig_mapa3_extra = ""
    # Mapa 4 só no corpo se Mapa 3 ausente (reduz redundância)
    fig_mapa_vuln = ""
    if maps.get("mapa_vulneraveis") and not maps.get("mapa_territorios"):
        fig_mapa_vuln = (
            "**Mapa 4 – Classificação ARARAS e populações vulneráveis "
            "(idosos e gestantes na APS)**\n\n"
            f"![Mapa 4]({maps.get('mapa_vulneraveis')})\n\n"
            f"Fonte: ARARAS MT/CIEVS-MT; e-SUS APS. Rodada de {semana.get('gerado_em_pt', '—')}."
        )
    anexo_mapa4 = ""
    if maps.get("mapa_vulneraveis") and maps.get("mapa_territorios"):
        anexo_mapa4 = (
            "\n### Mapa complementar — populações vulneráveis (anexo)\n\n"
            "**Mapa 4 – Classificação ARARAS e populações vulneráveis "
            "(idosos e gestantes na APS)**\n\n"
            f"![Mapa 4]({maps.get('mapa_vulneraveis')})\n\n"
            f"Fonte: ARARAS MT/CIEVS-MT; e-SUS APS. Rodada de {semana.get('gerado_em_pt', '—')}.\n"
        )

    obitos_fallback = (
        "### Óbitos sensíveis ao calor/clima (SIM)\n\n"
        "Dados SIM consolidados indisponíveis nesta rodada."
    )

    pauta = encaminhamentos(snap, publico=publico)

    rec_md = "\n".join(f"- {x}" for x in recs) if recs else f"- {INDISPONIVEL}"

    md = f"""# {titulo}
{f"**{SUBTITULO_SALA_SITUACAO}**" + chr(10) if USAR_TITULO_SALA_SITUACAO else ""}
**{SUBTITULO_INSTITUCIONAL} · Análise, Resposta e Acompanhamento de Riscos, Agravos e Saúde (ARARAS MT)**

Semana Epidemiológica {semana.get('semana', '—')}/{semana.get('ano', '—')} · {semana.get('periodo_pt', '—')}  
Atualizado em {semana.get('gerado_em_pt', semana.get('gerado_em', '—'))}

Referência climática: Painel El Niño 2026–2027, Boletim Mensal n.º 02, julho de 2026, e produtos oficiais de monitoramento climático, meteorológico, ambiental e hidrológico.  
Referência operacional: ARARAS MT, rodada de {semana.get('gerado_em_pt', '24/08/2026')}.  
Base normativa: Portaria n.º 0590/2026/GBSES.

{_bloco_atos_oficiais()}

Nota: a projeção operacional de aproximadamente 7 dias **não substitui** a previsão climática sazonal. Os produtos possuem objetivos e horizontes temporais distintos.

{_cards_executivos(snap)}

---

## 1. Leitura executiva da semana

{_leitura_executiva(snap)}

{_implicacao_operacional(snap)}

**Prioridades imediatas**

{_prioridades_imediatas()}

---

## 2. Cenário El Niño

**El Niño confirmado desde 11/06/2026.** Niño 3.4: {str(enso.get('nino34_recente') or '+1,4 °C').split('(')[0].strip()} (semanas anteriores). Persistência forte até o fim de 2026 (APCC/NOAA — Painel El Niño n.º {cenario.get('edicao', '02')}).

Fonte: Painel El Niño 2026–2027, boletim n.º {cenario.get('edicao', '02')}, {cenario.get('mes_referencia', 'julho de 2026')}.

---

## 3. Cenário sazonal — Brasil → Amazônia Legal → Mato Grosso

Trimestre ASO/2026 (CPTEC/INPE–INMET–FUNCEME): chuva abaixo da normal no centro-norte do País; temperatura acima da normal, com risco de ondas de calor, ar seco e queimadas.

- **Chuva (Brasil):** {br.get('chuva', INDISPONIVEL)} `{SELPREV}`
- **Temperatura (Brasil):** {br.get('temperatura', INDISPONIVEL)} `{SELPREV}`
- **Chuva em MT:** {mt.get('chuva', INDISPONIVEL)}
- **Temperatura em MT:** {mt.get('temperatura', INDISPONIVEL)}

### Comparação operacional — situação atual × série ambiental

{snap.get('serie_ambiente_md') or 'Série ambiental operacional ainda insuficiente nesta rodada.'}

_Fonte: painel ARARAS MT. A série operacional não substitui climatologia oficial de longo prazo._

{snap.get('sazonalidade_or_md') or ''}

{fig_sazonalidade}

---

## 4. Mato Grosso — Situação atual `{SELOBS}`

Distribuição atual: {fmt_distribuicao_niveis(snap.get('niveis'))}.

{fig_classes}

{tab_ind}

Cobertura dos indicadores: {fmt_frac(snap.get('cobertura_tmax'), snap.get('n_municipios'))} municípios. Preparação deve seguir o recorte mais exposto, não a mediana.

{(snap.get('rit') or {}).get('markdown') or ''}

{_bloco_irm_compostos(snap)}

---

## 5. Mato Grosso — Projeção operacional (~7 dias)

Distribuição projetada: {fmt_distribuicao_niveis(snap.get('niveis_projecao_7d'))}.

---

{mapa_md}

**Legenda:** {NIVEL_LEGENDA.get('verde')} · {NIVEL_LEGENDA.get('amarela')} · {NIVEL_LEGENDA.get('laranja')} · {NIVEL_LEGENDA.get('vermelha')} · {NIVEL_LEGENDA.get('roxa')}

---

## 7. Alertas meteorológicos e ambientais — Mato Grosso

Semana **{semana.get('rotulo', '—')}** ({semana.get('periodo_pt', '—')}). Recorte: **Mato Grosso** (avisos INMET exclusivos de MS excluídos).

{inmet.get('resumo_climatico_md', INDISPONIVEL)}

### INMET — síntese por fenômeno

**AVISOS VIGENTES NA EMISSÃO**

{inmet.get('inmet_vigentes_sintese_md') or inmet.get('inmet_vigentes_md', INDISPONIVEL)}

**AVISOS COM INÍCIO POSTERIOR NA SEMANA**

{inmet.get('inmet_futuros_sintese_md') or inmet.get('inmet_futuros_md') or '_Nenhum aviso com início posterior nesta consulta._'}

Consulta: {inmet.get('consulta_em', '—')}. Fonte: Alert-AS / INMET {inmet.get('citacao_inmet', cite('inmet_alertas'))}. Detalhe no painel.

### CEMADEN

{inmet.get('cemaden_md', INDISPONIVEL)}

Fonte: CEMADEN {inmet.get('citacao_cemaden', cite('cemaden_alertas'))}. Consulta: {inmet.get('consulta_em', '—')}.

### Síntese integrada

{inmet.get('titan_md', INDISPONIVEL)}

_Fontes: INMET, CEMADEN, solo, hidro e classificação ARARAS {cite('araras_mt')}._

---

## 8. Recursos hídricos / seca / estiagem

- {interpretar_hidrologia(snap)}
- Precipitação mediana no dia de referência: **{fmt_num(snap.get('precip_mediana'), 1, ' mm')}** · sem chuva: {fmt_frac(snap.get('n_sem_chuva'), snap.get('n_municipios'))}.
- Monitor de Secas (jun/2026): MT sem áreas classificadas com seca — produto defasado; cruzar com sinais locais.

{snap.get('impacto_chuva_md') or ''}

---

## 9. Fogo e qualidade do ar

{_narrativa(cenario, 'risco_fogo', str(mt.get('risco_fogo') or INDISPONIVEL))}

- {interpretar_fogo(snap)}
- IQA: {fmt_counts(snap.get('qualidade_ar'), ordem=['verde', 'amarela', 'laranja', 'vermelha', 'roxa', 'cinza'])}
- {interpretar_pm25(snap)}

Focos + PM2,5 reforçam vigilância respiratória nos prioritários.


---

## 10. Impactos potenciais à saúde

Associação temporal/espacial — **não implica causalidade**.

{tab_impactos}

### Monitoramento epidemiológico — dados observados

- **Respiratórios/fumaça:** {fmt_frac((agr.get('respiratorio_fumaca') or {}).get('municipios_pm25_25'), snap.get('n_municipios'))} com PM2,5 ≥ 25 µg/m³ em {ref_data}.
- **Calor/desidratação:** {_texto_calor_epidemiologico(snap)}
- **Arboviroses:** {fmt_int((agr.get('arboviroses_contexto_estiagem') or {}).get('casos_arbovirus_7d_soma'))} casos em 7 dias no recorte com dado (ausência não é zero).
- **Baixa disponibilidade hídrica:** {fmt_plural((snap.get('hydro_facts') or {}).get('low_availability'), 'município', 'municípios')} no recorte hidrológico disponível.
- **Risco elevado de inundação:** {fmt_plural((snap.get('hydro_facts') or {}).get('flood_risk_high'), 'município', 'municípios')} no recorte hidrológico disponível.

{_secao_agravos_dw(agr)}

{snap.get('esus_clima_md') or ''}

{fig_esus}

{secao_ondas_md}

{snap.get('obitos_clima_md') or obitos_fallback}

{analisar_cenario_bloco('Leitura epidemiológica', [
    'Associação temporal/espacial ≠ causalidade. Ler sinais com defasagem e cobertura de cada fonte.',
])}

---

## 11. Priorização territorial e acesso assistencial

{secao_reg}
### 11.2 Índice de prioridade de preparação clima–saúde

Municípios no extremo de atenção. Municípios prioritários para acompanhamento.

{pront_tab}

_{prontidao.get('nota', '')}_

---

### 11.2b Ocupação hospitalar (IndicaSUS) × pressão hospitalar (SISREG)

{bloco_ocup_sisreg}

---

### 11.3 Síntese territorial da semana

{sintese_territorial(snap)}

---

### 11.4 Povos indígenas, comunidades quilombolas, idosos, gestantes e acesso assistencial

{fig_mapa3_extra}

{fig_mapa_vuln}

**Municípios com aldeias indígenas em classes vermelha ou roxa**

{territorios.get('quadro_executivo_md') or territorios.get('quadro_md', INDISPONIVEL)}

_{territorios.get('nota_aldeias', '')}_
A lista completa permanece no painel operacional.

**Comunidades quilombolas certificadas em áreas de risco**

{territorios.get('quilombo_executivo_md') or territorios.get('quilombo_md', INDISPONIVEL)}

_{territorios.get('nota_quilombos', '')}_

**Geolocalização, classificação e distância da rede**

O Mapa 3 localiza aldeias (coordenada da aldeia) e municípios com quilombo certificado sobre a classe ARARAS. A tabela de acesso assistencial restringe o recorte a municípios **vermelhos ou roxos** com território longe da Atenção Primária à Saúde (APS) (> 30 km) ou do hospital (> 50 km).

{territorios.get('cobertura_md', INDISPONIVEL)}

{('_' + territorios['nota_cobertura'] + '_') if territorios.get('nota_cobertura') else ''}

{territorios.get('cobertura_recs_md') or ''}

### 11.5 Populações prioritárias e Saúde do Trabalhador

{populacoes_prioritarias(snap)}

**Saúde do Trabalhador e da Trabalhadora**

{saude_trabalhador(snap)}

---

## 12. Orientações operacionais por cenário climático

{orientacoes_por_cenario(snap)}

---

## 13. Orientações gerais sobre estoques e insumos

Dados específicos de estoque ainda não validados para esta rodada — as orientações abaixo são de preparação e **não** substituem programação farmacêutica nem prescrição clínica.

Até validação dos dados de estoques estratégicos estaduais, este boletim **não** publica quadro de estoques nem autonomia por item.

Orientações gerais para regionais e municípios sob pressão térmica/fumaça:
- Conferir autonomia de reidratação oral (SRO), soro endovenoso, broncodilatadores e hipoclorito conforme protocolos oficiais (RENAME, PCDT e notas técnicas do Ministério da Saúde / SES-MT).
- Reportar rupturas e risco de desabastecimento à Regional de Saúde com antecedência.
- Priorizar redistribuição e logística de última milha nos municípios em classes vermelha e roxa.
- **Não substitui** a programação farmacêutica municipal nem a prescrição clínica.

---

## 14. Recomendações oficiais aos estados e municípios `{SELSAZ}`

Fonte: Painel El Niño n.º {cenario.get('edicao', '—')} — não são gatilhos automáticos do ARARAS.

{rec_md}

## 15. Encaminhamentos

{pauta}

### Articulações intersetoriais recomendadas

{articulacao_intersetorial(snap)}

---

## 16. Notas metodológicas e glossário

- **Horizontes:** cenário sazonal (semanas/meses), situação atual (observado), projeção operacional de aproximadamente sete dias (ARARAS).
- **Tratamento de dados ausentes:** valores não disponíveis não são convertidos em zero.
- **Índice de prioridade de preparação:** expressa necessidade de preparação (maior = maior urgência); metodologia resumida abaixo.

{metodologia_indice_md()}
- **Medidor de trajetória:** não calculado nesta rodada por insuficiência de série temporal.
- **Série ambiental operacional:** média estadual diária (Open-Meteo / consolidação ARARAS) e qualidade do ar estadual; a comparação usa o **mesmo período do calendário** (mesmos dias MM-DD e/ou o mesmo mês) em anos anteriores da série — não mistura meses diferentes. Não substitui climatologia oficial.
- **Sazonalidade / Odds Ratio:** índice sazonal mensal, OR ecológico 2×2 (exposição climática × desfecho de saúde, limiares por quartil) e lags Spearman 0–14 dias; p<0,05 (Fisher/Spearman) destaca associação no recorte — **não** prova causalidade individual. Detalhe na aba Sazonalidade / OR.
- **GeoCalor / EHF (Fiocruz–LAGAS):** EHIsig = T3d − P95 local; EHIaccl = T3d − T30d; EHF = EHIsig × max(1, EHIaccl); evento ≥ 3 dias consecutivos com EHF > 0; intensidade pela distribuição local dos EHF positivos (EHF85). Cálculo estadual ARARAS para os 142 municípios (o portal GeoCalor não publica Cuiabá/MT).
- **Óbitos SIM sensíveis ao calor/clima:** ver metodologia abaixo e a aba homônima do painel.
- **Figuras e tabelas:** identificação acima e fonte abaixo (NBR 14724 / NBR 10719); referências bibliográficas em NBR 6023.

{snap.get('obitos_metodologia_md') or ''}

{snap.get('esus_clima_anexo_md') or ''}

{anexo_series_md}

{anexo_mapa4}

{documentacao_regra_projecao_md()}

{documentacao_rit_md()}

**Glossário**

{bloco_tabela(
        "Termos utilizados neste boletim",
        '''| Termo | Definição |
| --- | --- |
| Anomalia | Diferença entre o valor observado e a climatologia de referência. |
| Climatologia | Comportamento médio esperado para a região e a época. |
| Odds Ratio (OR) ecológico | Chance relativa do desfecho no grupo de municípios mais expostos vs menos expostos (análise agregada). |
| Índice sazonal | Razão entre a média do mês e a média geral do período (>1 = mês historicamente mais crítico). |
| PM2,5 | Partículas com diâmetro aerodinâmico de até 2,5 µm. |
| Percentil 95 | Valor acima do qual estão cerca de 5% das observações comparáveis. |
| EHF | Excess Heat Factor (Nairn & Fawcett) — índice de onda de calor do GeoCalor/Fiocruz. |
| EHIsig / EHIaccl | Componentes do EHF: significância térmica e aclimatização recente. |
| RIT | Risco Integrado Territorial (0–100): máximo entre domínios observados válidos; paralelo à projeção ~7d. |
| Domínio dominante | Domínio com maior escore no RIT do município. |
| Completude (RIT) | Percentual de domínios com dado válido na rodada. |
| Índice de prioridade de preparação | Score 0–100 (maior = maior urgência de preparação clima–saúde). |
| Índice de prioridade global | Score 0–100 do painel (vigilância, pressão, adaptação, fragilidade, alerta). |''',
        "Elaboração CIEVS-MT/ARARAS MT.",
    )}

---

## 17. Conclusão e tendência para a próxima semana

{conclusao_tendencia(snap, cenario, inmet)}

## REFERÊNCIAS

{chr(10).join(r for r in refs_biblio)}
"""
    return expand_siglas(numerar_tabelas(md))
