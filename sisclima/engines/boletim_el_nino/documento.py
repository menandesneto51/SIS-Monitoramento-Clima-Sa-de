# -*- coding: utf-8 -*-
"""Montagem do documento Markdown do boletim semanal El Niño."""
from __future__ import annotations

import json
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
from sisclima.engines.boletim_el_nino.orientacoes import (
    _texto_calor_epidemiologico,
    impactos_potenciais_saude,
    matriz_clima_saude_acao,
    orientacoes_por_cenario,
)
from sisclima.engines.boletim_el_nino.prontidao import metodologia_indice_md
from sisclima.engines.boletim_el_nino.referencias import cite


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
    esus_lines: list[str] = []
    fonte_esus = (
        "Fonte: Centralizador PEC/eSUS (esus2), cadastro vigente e atendimentos agregados "
        "nas janelas de 7 e 28 dias; classe ARARAS da rodada. Contagem operacional, não incidência."
    )
    if esus.get("status") == "ativo" and int(esus.get("municipios") or 0) > 0:
        class_rows = []
        for r in esus.get("por_classe") or []:
            if not isinstance(r, dict):
                continue
            class_rows.append(
                [
                    str(r.get("classe") or "—"),
                    fmt_int(r.get("municipios")),
                    fmt_int(r.get("asma")),
                    fmt_int(r.get("idoso_60mais")),
                    fmt_int(r.get("atendimentos_28d")),
                    fmt_int(r.get("nebulizacao_28d")),
                ]
            )
        mun_rows = []
        for r in esus.get("municipais") or esus.get("ranking_criticos") or []:
            if not isinstance(r, dict):
                continue
            mun_rows.append(
                [
                    str(r.get("municipio") or "—"),
                    str(r.get("classe_araras") or "—"),
                    fmt_int(r.get("asma")),
                    fmt_int(r.get("idoso_60mais")),
                    fmt_int(r.get("atendimentos_28d")),
                    fmt_int(r.get("resp_cid_28d")),
                    fmt_int(r.get("nebulizacao_28d") if r.get("nebulizacao_28d") is not None else r.get("nebulizacao_7d")),
                ]
            )
        esus_lines = [
            f"- **Atenção primária (Centralizador PEC/eSUS, {fmt_int(esus.get('municipios'))} municípios):** "
            f"cadastro **{fmt_int(esus.get('cadastros'))}** · asma **{fmt_int(esus.get('asma'))}** · "
            f"DPOC **{fmt_int(esus.get('dpoc'))}** · idosos 60+ **{fmt_int(esus.get('idoso_60mais'))}** · "
            f"gestantes **{fmt_int(esus.get('gestante'))}** · acamados **{fmt_int(esus.get('acamado'))}**.",
            f"- **Atendimentos na atenção primária:** **{fmt_int(esus.get('atendimentos_7d'))}** em 7 dias e "
            f"**{fmt_int(esus.get('atendimentos_28d'))}** em 28 dias "
            f"({fmt_int(esus.get('municipios_com_atendimento_28d'))} municípios com registro no período) · "
            f"CID respiratório 28d **{fmt_int(esus.get('resp_cid_28d'))}** · "
            f"nebulização 28d **{fmt_int(esus.get('nebulizacao_28d'))}** "
            f"(7d **{fmt_int(esus.get('nebulizacao_7d'))}**).",
            f"- **classes vermelha e roxa ARARAS:** {fmt_int(esus.get('municipios_vermelho_roxo'))} municípios "
            "com cadastro na atenção primária. Contagem operacional; não é incidência nem diagnóstico.",
        ]
        atraso = int(esus.get("atraso_dias") or 0)
        if atraso > 0 or esus.get("janela_ancorada"):
            esus_lines.append(
                f"- **Atualidade da carga de atendimentos:** última data válida no Centralizador "
                f"**{esus.get('data_max_atendimento') or '—'}** "
                f"(atraso de **{fmt_int(atraso)}** dia(s)"
                + (
                    f"; janela 7d/28d ancorada em **{esus.get('data_janela_fim') or esus.get('data_max_atendimento') or '—'}**"
                    if esus.get("janela_ancorada")
                    else ""
                )
                + "). Ausência de município no período **não** significa zero clínico — "
                "pode ser atraso de envio ao `esus2`."
            )
        if class_rows:
            esus_lines.extend(
                [
                    "",
                    "**Tabela – PEC/eSUS por classe ARARAS (universo estadual)**",
                    "",
                    md_table(
                        ["Classe", "Municípios", "Asma (cad.)", "Idoso 60+", "Atend. 28d", "Nebulização 28d"],
                        class_rows,
                    ),
                    "",
                    fonte_esus,
                ]
            )
        if mun_rows:
            esus_lines.extend(
                [
                    "",
                    "**Tabela – PEC/eSUS por município (universo estadual)**",
                    "",
                    md_table(
                        [
                            "Município",
                            "Classe",
                            "Asma (cad.)",
                            "Idoso 60+",
                            "Atend. 28d",
                            "CID resp. 28d",
                            "Nebulização 28d",
                        ],
                        mun_rows,
                    ),
                    "",
                    fonte_esus,
                ]
            )

    return "\n".join(
        [
            "",
            f"### Epidemiologia operacional (janela {janela} dias)",
            "",
            f"- **Intoxicação exógena (sinal de fumaça):** {_v(intox.get('notificacoes_intox_total_7d'))} notificações; "
            f"**{_v(intox.get('notificacoes_fumaca_7d'))}** com sinal de fumaça.",
            _internacao_linha(),
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


def _secao_ondas_calor(snap: dict[str, Any], maps: dict[str, Any] | None = None) -> str:
    """Ondas de calor — sem nomenclatura STAR; foco operacional ARARAS."""
    maps = maps or {}
    n = snap.get("n_municipios")
    n_onda = snap.get("n_onda_calor")
    n_tmax = snap.get("n_tmax_37")
    ext = (snap.get("extremos") or {}).get("tmax") or {}
    tmax_max = ext.get("tmax")
    linhas = [
        "",
        "### Ondas de calor",
        "",
        "Monitoramento operacional ARARAS: persistência térmica (P95 ≥ 2 dias) e UTCI, "
        "complementados pelo Excess Heat Factor (EHF) quando a série climática estiver disponível. "
        "**Não substitui** avisos oficiais do INMET.",
        "",
        f"- **Calor extremo nesta rodada:** Tmáx máxima **{fmt_num(tmax_max, 1, ' °C')}** · "
        f"**{fmt_frac(n_tmax, n)}** com Tmáx ≥ 37 °C · "
        f"sinal de onda (P95≥2d) em **{fmt_frac(n_onda, n)}**.",
        f"- **Classes vermelha e roxa:** **{fmt_frac(snap.get('n_vermelha_roxa'), n)}** agora; "
        f"projeção ~7 dias em **{fmt_frac(int((snap.get('niveis_projecao_7d') or {}).get('vermelha') or 0) + int((snap.get('niveis_projecao_7d') or {}).get('roxa') or 0), n)}**.",
    ]
    if maps.get("serie_climatica"):
        ini = maps.get("serie_climatica_inicio") or "—"
        fim = maps.get("serie_climatica_fim") or "—"
        linhas.extend(
            [
                "",
                f"**Figura – Série climática operacional (Tmáx estadual mensal, {ini} a {fim})**",
                "",
                f"![Série climática Tmáx]({maps.get('serie_climatica')})",
                "",
                f"Fonte: grade operacional ARARAS MT (história climática municipal). Série disponível a partir de {ini}.",
            ]
        )
    linhas.extend(
        [
            "",
            "Fonte: ARARAS MT/CIEVS-MT. Contagem operacional — não é incidência nem causalidade individual.",
        ]
    )
    return "\n".join(linhas)


def _cards_executivos(snap: dict[str, Any]) -> str:
    """Seis cartões do resumo — substitui a tabela operacional da primeira página."""
    if not snap.get("disponivel"):
        return INDISPONIVEL
    n = snap.get("n_municipios")
    crit = snap.get("n_vermelha_roxa")
    proj = snap.get("niveis_projecao_7d") or {}
    proj_crit = int(proj.get("vermelha") or 0) + int(proj.get("roxa") or 0)
    ext = (snap.get("extremos") or {}).get("tmax") or {}
    pct = ""
    if crit is not None and n:
        pct = f"{fmt_num(100.0 * float(crit) / float(n), 1, '%')} do estado"
    return f"""| RISCO ATUAL | PROJEÇÃO ~7 DIAS | CALOR |
| --- | --- | --- |
| **{fmt_int(crit)}/{fmt_int(n)}** vermelho ou roxo | **{fmt_int(proj_crit)}/{fmt_int(n)}** vermelho ou roxo | máxima **{fmt_num(ext.get('tmax'), 1, ' °C')}** |
| {pct} | agravamento disseminado | **{fmt_frac(snap.get('n_tmax_37'), n)}** ≥ 37 °C |

| UMIDADE | FOGO | QUALIDADE DO AR |
| --- | --- | --- |
| **{fmt_frac(snap.get('n_umidade_30'), n)}** ≤ 30% | **{fmt_int(snap.get('focos_7d_total'))}** focos de calor | **{fmt_frac(snap.get('n_pm25_25'), n)}** ≥ 25 µg/m³ |
| mediana {fmt_num(snap.get('umidade_mediana'), 0, '%')} | Satélite de referência do Programa Queimadas · 7 dias · {fmt_int(snap.get('n_com_focos_7d'))} municípios · {fmt_int(snap.get('deteccoes_7d_total'))} detecções multi-satélite | máximo {fmt_num(snap.get('pm25_max'), 1, ' µg/m³')} |
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
    n37 = int(snap.get("n_tmax_37") or 0)
    n25 = int(snap.get("n_pm25_25") or 0)
    n30 = int(snap.get("n_umidade_30") or 0)
    expos: list[str] = []
    if n37 > 0:
        expos.append("calor extremo")
    if n30 > 0:
        expos.append("ar seco")
    if n25 > 0:
        expos.append("material particulado elevado")
    if len(expos) >= 2:
        exp_txt = ", ".join(expos[:-1]) + " e " + expos[-1]
    elif expos:
        exp_txt = expos[0]
    else:
        exp_txt = "exposições climáticas relevantes"
    return (
        f"Distribuição atual: {fmt_distribuicao_niveis(niveis)}. "
        f"A mediana estadual não descreve o recorte mais exposto: há municípios com {exp_txt}. "
        "A projeção de sete dias indica agravamento "
        "disseminado e recomenda preparação assistencial nos territórios já em vermelho ou roxo, "
        "incluindo populações indígenas, quilombolas e trabalhadores expostos."
    )


def _implicacao_operacional(snap: dict[str, Any]) -> str:
    """Frase dinâmica conforme presença de calor, fumaça e baixa umidade na rodada."""
    n37 = int(snap.get("n_tmax_37") or 0)
    n25 = int(snap.get("n_pm25_25") or 0)
    n30 = int(snap.get("n_umidade_30") or 0)
    eixos: list[str] = []
    if n37 > 0:
        eixos.append("calor intenso")
    if n25 > 0:
        eixos.append("exposição à fumaça")
    if len(eixos) >= 2:
        nucleo = f"A combinação de {eixos[0]} e {eixos[1]}"
    elif eixos:
        nucleo = f"A presença de {eixos[0]}"
    else:
        nucleo = "O cenário operacional da rodada"
    if n30 == 1:
        nucleo += ", com ocorrência localizada de baixa umidade"
    elif n30 > 1:
        nucleo += ", com baixa umidade em múltiplos municípios"
    return (
        f"**Implicação operacional.** {nucleo} justifica reforçar a vigilância, "
        "revisar a capacidade assistencial e verificar a disponibilidade de insumos "
        "nos territórios prioritários."
    )


def _leitura_regional_curta(snap: dict[str, Any]) -> str:
    """2–4 frases a partir da tabela de regionais — sem repetir todas as linhas."""
    regs = list(snap.get("regionais") or [])
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
    # macrorregião aproximada pelo nome das duas primeiras
    top2 = [str(r.get("regional") or "") for r in regs[:2] if r.get("regional")]
    if len(top2) == 2:
        frases.append(
            f"A atenção imediata permanece nas regionais **{top2[0]}** e **{top2[1]}**, "
            "com reforço assistencial nos municípios já em vermelho ou roxo."
        )
    return " ".join(frases[:4])


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
        "- Reforçar vigilância de agravos relacionados a calor e fumaça nos municípios em vermelho ou roxo.\n"
        "- Revisar capacidade assistencial e insumos nos territórios com Tmáx ≥ 37 °C ou PM2,5 ≥ 25 µg/m³.\n"
        "- Articular regionais, DSEI/SESAI e Vigilância em Saúde do Trabalhador nos recortes prioritários."
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
        f"**{q.get('ocupacao_n_sem_leitos') or '—'}** sem leitos elegíveis no recorte SIEGES"
        + (f" · {q.get('unidades_n')} unidades" if q.get("unidades_n") else ""),
        f"- Pressão SISREG: **{q.get('sisreg_n') or '—'}** municípios · "
        f"solicitações média {q.get('sisreg_solicitacoes_media_txt') or '—'} · "
        f"máx {q.get('sisreg_solicitacoes_max_txt') or '—'}",
        f"- Filtros: _{q.get('filtros_sieges_txt') or 'SIEGES'}_",
        "",
        f"_{q.get('nota_separacao')}_",
    ]

    por_reg = q.get("ocupacao_por_regional") or []
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
                "Municípios sem leitos no recorte não entram no denominador do %. "
                "UTI por regional permanece pendente de mapeamento TipoLeito no IndicaSUS._",
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
            rows.append(
                [
                    str(r.get("municipio") or "—"),
                    str(r.get("regional") or "—"),
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


def _bloco_atos_oficiais() -> str:
    try:
        from sisclima.reporting.decretos_alerta import bloco_decretos_markdown_boletim

        return bloco_decretos_markdown_boletim()
    except Exception:  # noqa: BLE001
        return ""


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
        linhas_reg.append(
            [
                str(r.get("regional") or "—"),
                fmt_int(r.get("n_vermelha_roxa")),
                str(r.get("tendencia_7d") or "—"),
                fmt_num(r.get("tmax_mediana"), 1, " °C"),
            ]
        )
    tab_reg = bloco_tabela(
        "Regionais de saúde com maior concentração de municípios nas classes vermelha e roxa",
        md_table(
            ["Regional", "Municípios em vermelho/roxo (atual)", "Mudança ~7 dias", "Tmáx mediana"],
            linhas_reg if snap.get("disponivel") else [],
        ),
        "ARARAS MT/CIEVS-MT, classificação municipal agregada por regional de saúde.",
        nota=(
            "↑ indica aumento da classificação; → estabilidade; ↓ redução, "
            "considerando todos os municípios da Regional."
        ),
    )
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
    if maps.get("grafico_classes"):
        fig_classes = (
            f"![Classes ARARAS]({maps.get('grafico_classes')})\n\n"
            "Fonte: ARARAS MT/CIEVS-MT — contagem municipal por classe na rodada."
        )
    fig_esus = ""
    if maps.get("grafico_esus_vulneraveis"):
        fig_esus = (
            "**Figura – Vulneráveis na APS por classe ARARAS**\n\n"
            f"![Vulneráveis APS]({maps.get('grafico_esus_vulneraveis')})\n\n"
            "Fonte: e-SUS APS (cadastro) × classe ARARAS da rodada."
        )
    if maps.get("mapa_vulneraveis"):
        fig_mapa_vuln = (
            "**Mapa 4 – Classificação ARARAS e populações vulneráveis "
            "(indígenas, quilombolas, idosos e gestantes)**\n\n"
            f"![Mapa 4]({maps.get('mapa_vulneraveis')})\n\n"
            f"Fonte: ARARAS MT/CIEVS-MT; FUNAI (aldeias); Fundação Cultural Palmares (quilombos); "
            f"e-SUS APS (idosos/gestantes em municípios vermelhos/roxos). Rodada de {semana.get('gerado_em_pt', '—')}.\n"
            "Nota: aldeias por coordenada disponível; quilombos sem coordenada validada aparecem como presença municipal. "
            "Bolhas de idosos/gestantes são escala visual do cadastro APS — não são incidência."
        )
    else:
        fig_mapa_vuln = ""
    fig_mapa3_extra = ""
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
        fig_mapa3_extra = (
            "**Mapa 3 – Classificação de risco climático, aldeias indígenas e municípios com "
            "comunidades quilombolas certificadas em Mato Grosso**\n\n"
            "![Mapa 3](_assets_SE_34-2026/mapa_territorios_tradicionais.png)\n\n"
            "Fonte: FUNAI e Fundação Cultural Palmares sobre classes ARARAS."
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

> A projeção operacional de aproximadamente 7 dias **não substitui** a previsão climática sazonal. Os produtos possuem objetivos e horizontes temporais distintos.

{_cards_executivos(snap)}

---

## 1. Leitura executiva da semana

{_leitura_executiva(snap)}

{_implicacao_operacional(snap)}

**Prioridades imediatas**

{_prioridades_imediatas()}

---

## 2. Cenário El Niño

**El Niño confirmado desde 11/06/2026.**  
**Niño 3.4:** anomalia de {str(enso.get('nino34_recente') or '+1,4 °C').split('(')[0].strip()} nas semanas anteriores ao boletim.

{_narrativa(cenario, 'perspectivas', enso.get('persistencia', INDISPONIVEL))}

Fonte: Painel El Niño 2026–2027, boletim n.º {cenario.get('edicao', '02')}, {cenario.get('mes_referencia', 'julho de 2026')}.

---

## 3. Cenário sazonal — Brasil → Amazônia Legal → Mato Grosso

{_narrativa(cenario, 'previsao_aso', str(br.get('chuva') or INDISPONIVEL))}

- **Chuva (Brasil):** {br.get('chuva', INDISPONIVEL)} `{SELPREV}`
- **Temperatura (Brasil):** {br.get('temperatura', INDISPONIVEL)} `{SELPREV}`

### Amazônia Legal e Mato Grosso

{_narrativa(cenario, 'amazonia_legal', str(mt.get('chuva') or INDISPONIVEL))}

- **Chuva em MT:** {mt.get('chuva', INDISPONIVEL)}
- **Temperatura em MT:** {mt.get('temperatura', INDISPONIVEL)}

### Comparação operacional — situação atual × série ambiental

{snap.get('serie_ambiente_md') or 'Série ambiental operacional ainda insuficiente nesta rodada para comparação formal com o histórico.'}

_Fonte: painel ARARAS MT (abas Série ambiental e Sazonalidade / OR). A série operacional não substitui a climatologia oficial de longo prazo._

---

## 4. Mato Grosso — Situação atual `{SELOBS}`

Distribuição atual: {fmt_distribuicao_niveis(snap.get('niveis'))}.

{fig_classes}

{tab_ind}

Cobertura dos quatro indicadores: {fmt_frac(snap.get('cobertura_tmax'), snap.get('n_municipios'))} municípios.

**O que isso significa para esta semana?** A mediana não descreve o recorte mais exposto. {_frase_exposicao_rodada(snap)} a preparação deve concentrar-se nesses municípios, e não na média.

---

## 5. Mato Grosso — Projeção operacional (~7 dias)

A projeção operacional do ARARAS MT estima a classificação municipal para aproximadamente sete dias, permitindo comparação com a situação atual.

Distribuição projetada: {fmt_distribuicao_niveis(snap.get('niveis_projecao_7d'))}

---

{mapa_md}

**Legenda:** {NIVEL_LEGENDA.get('verde')} · {NIVEL_LEGENDA.get('amarela')} · {NIVEL_LEGENDA.get('laranja')} · {NIVEL_LEGENDA.get('vermelha')} · {NIVEL_LEGENDA.get('roxa')}

---

## 7. Alertas meteorológicos e ambientais — Mato Grosso

Parâmetro climático oficial para a semana **{semana.get('rotulo', '—')}** ({semana.get('periodo_pt', '—')}).

_Recorte territorial: **Estado de Mato Grosso**. O Instituto Nacional de Meteorologia (INMET) lista apenas avisos que abrangem Mato Grosso; trechos exclusivos de Mato Grosso do Sul são excluídos._

{inmet.get('resumo_climatico_md', INDISPONIVEL)}

### INMET — síntese por fenômeno

**AVISOS VIGENTES NA EMISSÃO**

{inmet.get('inmet_vigentes_sintese_md') or inmet.get('inmet_vigentes_md', INDISPONIVEL)}

**AVISOS COM INÍCIO POSTERIOR NA SEMANA**

{inmet.get('inmet_futuros_sintese_md') or inmet.get('inmet_futuros_md') or '_Nenhum aviso com início posterior registrado nesta consulta._'}

Consulta: {inmet.get('consulta_em', '—')}. Fonte: feed Alert-AS / portal INMET {inmet.get('citacao_inmet', cite('inmet_alertas'))}.
A lista completa dos avisos permanece no painel operacional.

### Centro Nacional de Monitoramento e Alertas de Desastres Naturais (CEMADEN)

{inmet.get('cemaden_md', INDISPONIVEL)}

Fonte: Painel CEMADEN {inmet.get('citacao_cemaden', cite('cemaden_alertas'))}. Consulta: {inmet.get('consulta_em', '—')}.

### Síntese integrada de alertas meteorológicos e ambientais

{inmet.get('titan_md', INDISPONIVEL)}

_Fontes integradas: INMET, CEMADEN, saturação do solo, risco hidrológico e classificação ARARAS {cite('araras_mt')}._

---

## 8. Recursos hídricos / seca / estiagem

{_narrativa(cenario, 'centro_oeste_monitor', str(mt.get('monitor_secas_jun2026') or INDISPONIVEL))}

- {interpretar_hidrologia(snap)}
- Precipitação mediana no **dia de referência operacional**: **{fmt_num(snap.get('precip_mediana'), 1, ' mm')}** · municípios sem chuva nesse dia: {fmt_frac(snap.get('n_sem_chuva'), snap.get('n_municipios'))}

{analisar_cenario_bloco('O que isso significa para esta semana?', [
    'No Monitor de Secas de junho de 2026, Mato Grosso não apresentava áreas classificadas com seca. A defasagem temporal desse produto e os sinais locais desta rodada recomendam interpretação conjunta, sem extrapolação estadual.',
])}

---

## 9. Fogo e qualidade do ar

{_narrativa(cenario, 'risco_fogo', str(mt.get('risco_fogo') or INDISPONIVEL))}

- {interpretar_fogo(snap)}
- IQA (classes, ordem operacional): {fmt_counts(snap.get('qualidade_ar'), ordem=['verde', 'amarela', 'laranja', 'vermelha', 'roxa', 'cinza'])}
- {interpretar_pm25(snap)}

A combinação de focos de calor e material particulado fino reforça a vigilância de agravos respiratórios nos municípios prioritários.


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

{_secao_ondas_calor(snap, maps)}

{snap.get('obitos_clima_md') or obitos_fallback}

{analisar_cenario_bloco('Leitura epidemiológica', [
    'Associação temporal e espacial não implica causalidade. Sinais assistenciais e de notificação devem ser lidos com a defasagem das fontes e com a cobertura de cada indicador.',
])}

---

## 11. Priorização territorial e acesso assistencial

### 11.1 Regionais de Saúde

{tab_reg}

{_leitura_regional_curta(snap)}

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

{fig_mapa_vuln}

{fig_mapa3_extra}

**Municípios com aldeias indígenas em classes vermelha ou roxa**

{territorios.get('quadro_executivo_md') or territorios.get('quadro_md', INDISPONIVEL)}

_{territorios.get('nota_aldeias', '')}_
A lista completa permanece no painel operacional.

**Comunidades quilombolas certificadas em áreas de risco**

{territorios.get('quilombo_executivo_md') or territorios.get('quilombo_md', INDISPONIVEL)}

_{territorios.get('nota_quilombos', '')}_

**Geolocalização, classificação e distância da rede**

O Mapa 3 localiza aldeias (coordenada da aldeia) e municípios com quilombo certificado sobre a classe ARARAS. A Tabela 7 restringe o recorte a municípios **vermelhos ou roxos** com território longe da Atenção Primária à Saúde (APS) (> 30 km) ou do hospital (> 50 km).

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

## 13. Orientações de estoques e insumos (provisório)

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
- **Série ambiental operacional:** média estadual diária (Open-Meteo / consolidação ARARAS) e qualidade do ar estadual; a comparação “janela atual × restante da série” é descritiva e não substitui climatologia oficial.
- **Óbitos SIM sensíveis ao calor/clima:** ver metodologia abaixo e a aba homônima do painel.
- **Figuras e tabelas:** identificação acima e fonte abaixo (NBR 14724 / NBR 10719); referências bibliográficas em NBR 6023.

{snap.get('obitos_metodologia_md') or ''}

{documentacao_regra_projecao_md()}

**Glossário**

{bloco_tabela(
        "Termos utilizados neste boletim",
        '''| Termo | Definição |
| --- | --- |
| Anomalia | Diferença entre o valor observado e a climatologia de referência. |
| Climatologia | Comportamento médio esperado para a região e a época. |
| PM2,5 | Partículas com diâmetro aerodinâmico de até 2,5 µm. |
| Percentil 95 | Valor acima do qual estão cerca de 5% das observações comparáveis. |
| Índice de prioridade de preparação | Score 0–100 (maior = maior urgência de preparação clima–saúde). |
| Índice de prioridade global | Score 0–100 do painel (vigilância, pressão, adaptação, fragilidade, alerta). |''',
        "Elaboração CIEVS-MT/ARARAS MT.",
    )}

---

## 17. Conclusão e tendência para a próxima semana

{conclusao_tendencia(snap, cenario, inmet)}

## 18. Referências

{chr(10).join(r for r in refs_biblio)}
"""
    return expand_siglas(numerar_tabelas(md))
