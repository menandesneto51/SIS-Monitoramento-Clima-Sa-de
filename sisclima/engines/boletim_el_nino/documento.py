# -*- coding: utf-8 -*-
"""Montagem do documento Markdown do boletim semanal El Niño."""
from __future__ import annotations

from typing import Any

from sisclima.engines.boletim_el_nino.constants import (
    INDISPONIVEL,
    NAO_CALCULADO,
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
    expand_siglas,
    fmt_counts,
    fmt_date_pt,
    fmt_frac,
    fmt_int,
    fmt_metric_box,
    fmt_num,
    humanize_label,
    md_table,
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
from sisclima.engines.boletim_el_nino.orientacoes import (
    impactos_potenciais_saude,
    matriz_clima_saude_acao,
    orientacoes_por_cenario,
)
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
                f"- **Internações (janela operacional):** total **{_v(total)}** · "
                f"respiratório/alérgico **{_v(grupos.get('resp_alergico'))}** · "
                f"desidratação/calor **{_v(grupos.get('desidratacao_calor'))}**."
            )
        mes_total = intern.get("internacoes_ultimo_mes_dw")
        if mes_total is not None:
            return (
                f"- **Internações (janela {janela} dias):** dado não disponível na janela curta. "
                f"Competência mensal mais recente (**{intern.get('mes_competencia_dw', '—')}**): "
                f"**{fmt_int(mes_total)}** internações · "
                f"respiratório/alérgico **{_v(grupos_mes.get('resp_alergico'))}** · "
                f"desidratação/calor **{_v(grupos_mes.get('desidratacao_calor'))}**."
            )
        return (
            "- **Internações hospitalares:** dados não estavam disponíveis para esta rodada."
        )

    return "\n".join(
        [
            "",
            f"### Epidemiologia operacional (janela {janela} dias)",
            "",
            f"- **Intoxicação exógena (sinal de fumaça):** {_v(intox.get('notificacoes_intox_total_7d'))} notificações; "
            f"**{_v(intox.get('notificacoes_fumaca_7d'))}** com sinal de fumaça.",
            _internacao_linha(),
        ]
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
        f"- **{fmt_int(focos)} focos** — acumulado de sete dias.",
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
        # Base só com detecções: não exibir cob/n como cobertura estadual
        if cob_focos is not None and n_com_focos is not None and int(cob_focos) == int(n_com_focos):
            cob_fogo_txt = "não caracterizada por esta estrutura da base"
            situ_fogo = (
                f"Focos detectados em {fmt_int(n_com_focos)} de {fmt_int(n)} municípios"
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
                fmt_num(snap.get("tmax_mediana"), 1, " °C"),
            ],
            [
                "Umidade",
                "Atenção" if (snap.get("n_umidade_30") or 0) > 0 else "Sem alerta operacional",
                "não calculada",
                fmt_frac(snap.get("cobertura_umidade"), n),
                fmt_num(snap.get("umidade_mediana"), 0, "%"),
            ],
            [
                "Fogo",
                situ_fogo,
                _tend_vocab("fogo"),
                cob_fogo_txt,
                f"{fmt_int(snap.get('focos_7d_total'))} focos (7 dias)",
            ],
            [
                "Qualidade do ar",
                situ_ar,
                _tend_vocab("ar"),
                fmt_frac(snap.get("cobertura_pm25") or snap.get("cobertura_tmax"), n),
                fmt_num(snap.get("pm25_mediana"), 1, " µg/m³"),
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
        + "\n\n_Nota: referências operacionais — Painel El Niño/NOAA; Tmáx e UR medianas municipais; "
        "focos INPE (7 dias); PM2,5 mediano; situação hidrológica municipal; classificação ARARAS._"
    )


def _mapa_sintese(snap: dict[str, Any]) -> str:
    if not snap.get("disponivel"):
        return INDISPONIVEL
    atual = snap.get("niveis") or {}
    proj = snap.get("niveis_projecao_7d") or {}
    delta = snap.get("delta_projecao") or {}

    def _linhas(d: dict[str, int]) -> str:
        from sisclima.engines.boletim_el_nino.formatters import fmt_plural

        parts = []
        for k in ("amarela", "laranja", "vermelha", "roxa"):
            if k in d:
                parts.append(f"- {_label_nivel(k)}: {fmt_plural(d[k], 'município', 'municípios')}")
        return "\n".join(parts) if parts else INDISPONIVEL

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

    return f"""**Situação atual** `{SELOBS}`
{_linhas(atual)}

**Projeção ~7 dias** `{SELPROJ}`
{_linhas(proj)}

**Mudança esperada**
{mudanca}"""


def _label_nivel(k: str) -> str:
    return {"amarela": "Amarelo", "laranja": "Laranja", "vermelha": "Vermelho", "roxa": "Roxo"}.get(k, k)


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

    titulo = (
        "Relatório semanal El Niño — ARARAS MT"
        if publico
        else "RELATÓRIO SEMANAL EL NIÑO"
    )
    secao_mun = (
        "Municípios prioritários para acompanhamento"
        if publico
        else "Municípios prioritários para resposta e preparação"
    )

    n_mun_txt = fmt_int(snap.get("n_municipios")) if snap.get("disponivel") else INDISPONIVEL
    raw_ref = snap.get("data_referencia") or "rodada atual"
    ref_data = fmt_date_pt(raw_ref) if raw_ref not in {"rodada atual", None} else str(raw_ref)

    linhas_top: list[list[str]] = []
    for p in snap.get("prioritarios") or []:
        linhas_top.append(
            [
                str(p.get("municipio") or "—"),
                str(p.get("regional_saude") or "—"),
                str(p.get("nivel") or "—").title() if p.get("nivel") else "—",
                str(p.get("nivel_predicao_7d") or INDISPONIVEL).title()
                if p.get("nivel_predicao_7d")
                else INDISPONIVEL,
                fmt_num(p.get("tmax"), 1, " °C"),
                fmt_num(p.get("umidade_media"), 0, "%"),
                fmt_num(p.get("pm25_ugm3"), 1, " µg/m³"),
                fmt_int(p.get("focos_queimadas_7d")),
            ]
        )
    tab_prior = md_table(
        ["Município", "Regional", "Atual", "~7 dias", "Tmáx", "UR", "PM2,5", "Focos 7d"],
        linhas_top if snap.get("disponivel") else [],
    )

    linhas_reg: list[list[str]] = []
    for r in (snap.get("regionais") or [])[:12]:
        linhas_reg.append(
            [
                str(r.get("regional") or "—"),
                fmt_int(r.get("n_amarela_plus")),
                fmt_int(r.get("n_laranja_plus")),
                fmt_int(r.get("n_vermelha_roxa")),
                fmt_counts(r.get("tendencia_7d")) if r.get("tendencia_7d") else INDISPONIVEL,
                fmt_num(r.get("tmax_mediana"), 1, " °C"),
            ]
        )
    tab_reg = md_table(
        ["Regional", "Amarelo+", "Laranja+", "Verm.+Roxa", "Tend. ~7d", "Tmáx med."],
        linhas_reg if snap.get("disponivel") else [],
    )

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
**Mapa 1 – Classificação integrada de risco em Mato Grosso, {semana.get('periodo_pt', '')} (atual e ~7 dias)**

![Mapa 1]({maps.get('mapa_atual_projecao')})

Fonte: ARARAS MT/CIEVS-MT, rodada de {semana.get('gerado_em_pt', semana.get('gerado_em'))}.
Nota: as duas faces usam a mesma escala de classes (verde a roxo) para comparação visual direta.

**Mapa 2 – Variação projetada da classificação de risco em aproximadamente sete dias**

![Mapa 2]({maps.get('mapa_delta')})

Fonte: ARARAS MT/CIEVS-MT, rodada de {semana.get('gerado_em_pt', semana.get('gerado_em'))}.
Municípios com dados comparáveis: {fmt_frac(n_delta, snap.get('n_municipios'))}.
- Melhora: {fmt_frac(dc.get('melhora'), n_delta)}
- Estabilidade: {fmt_frac(dc.get('estabilidade'), n_delta)}
- Aumento de 1 nível: {fmt_frac(dc.get('aumento_1'), n_delta)}
- Aumento de 2 ou mais níveis: {fmt_frac(dc.get('aumento_2plus'), n_delta)}
{f"- Sem pareamento válido: {fmt_int(sem_par)}" if sem_par else ""}

{interp_delta}

{snap.get("determinantes_projecao_md") or ""}

{_mapa_sintese(snap)}
"""
    else:
        mapa_md = f"_{maps.get('motivo', INDISPONIVEL)}_"

    pauta = encaminhamentos(snap, publico=publico)

    rec_md = "\n".join(f"- {x}" for x in recs) if recs else f"- {INDISPONIVEL}"

    md = f"""# {titulo}

**Sala de Situação do Centro Integrado de Vigilância Epidemiológica e Sanitária de Mato Grosso (CIEVS-MT) · Análise, Resposta e Acompanhamento de Riscos, Agravos e Saúde (ARARAS MT)**

Semana Epidemiológica {semana.get('semana', '—')}/{semana.get('ano', '—')} · {semana.get('periodo_pt', '—')}  
Atualizado em {semana.get('gerado_em_pt', semana.get('gerado_em', '—'))}

Padrão de referência: Painel El Niño 2026–2027, boletim mensal n.º {cenario.get('edicao', '—')} ({cenario.get('mes_referencia', '—')}) · trimestre {cenario.get('trimestre', 'ASO/2026')} {cite_painel}.  
Dados operacionais: ARARAS MT · referência **{ref_data}**.
Fontes climáticas oficiais consultadas incluem o Instituto Nacional de Meteorologia (INMET) e o Centro Nacional de Monitoramento e Alertas de Desastres Naturais (CEMADEN).
Indicadores climáticos de referência: temperatura máxima (Tmáx), umidade relativa (UR) e material particulado fino com diâmetro aerodinâmico de até 2,5 µm (PM2,5).

{box_base_normativa()}

> A projeção operacional de aproximadamente 7 dias **não substitui** a previsão climática sazonal. Os produtos possuem objetivos e horizontes temporais distintos.

---

## 1. Resumo executivo

{_painel_semaforo(snap, cenario)}

{_destaques_executivos(snap)}

**Preparação assistencial induzida pelo clima:** quando há convergência de calor, baixa umidade e fumaça, avaliar capacidade assistencial, comunicação de risco e cobertura de estoques relacionados aos agravos esperados — sem substituir decisão da gestão.

- **Cenário:** {enso.get('status', INDISPONIVEL)} · intensidade {enso.get('intensidade', INDISPONIVEL)}
- **Território MT:** {fmt_frac(snap.get('n_vermelha_roxa'), snap.get('n_municipios'))} nas classes vermelha ou roxa
- **Onde priorizar:** consultar mapas e municípios prioritários (seções 6 e 11)

---

## 2. Cenário El Niño

{_narrativa(cenario, 'situacao_atual', str(enso.get('status') or INDISPONIVEL))}

| Indicador | Observado | Referência |
| --- | --- | --- |
| ENSO | {enso.get('status', INDISPONIVEL)} | classificação oficial da fonte |
| Niño 3.4 | {enso.get('nino34_recente', INDISPONIVEL)} | limiares NOAA / Painel El Niño |

{_narrativa(cenario, 'perspectivas', enso.get('persistencia', INDISPONIVEL))}

Fonte: Painel El Niño 2026–2027, boletim n.º {cenario.get('edicao', '—')}, {cenario.get('mes_referencia', 'jul./2026')}.

---

## 3. Cenário sazonal — Brasil → Amazônia Legal → Mato Grosso

{_narrativa(cenario, 'previsao_aso', str(br.get('chuva') or INDISPONIVEL))}

- **Chuva (Brasil):** {br.get('chuva', INDISPONIVEL)} `{SELPREV}`
- **Temperatura (Brasil):** {br.get('temperatura', INDISPONIVEL)} `{SELPREV}`

### Amazônia Legal e Mato Grosso

{_narrativa(cenario, 'amazonia_legal', str(mt.get('chuva') or INDISPONIVEL))}

- **Chuva em MT:** {mt.get('chuva', INDISPONIVEL)}
- **Temperatura em MT:** {mt.get('temperatura', INDISPONIVEL)}

---

## 4. Mato Grosso — Situação atual `{SELOBS}`

Municípios no recorte: **{n_mun_txt}**  
Níveis: classes vermelha e roxa **{fmt_int(snap.get('n_vermelha_roxa'))}** · laranja **{fmt_int(snap.get('n_laranja'))}** · amarelo **{fmt_int(snap.get('n_amarela'))}** · detalhe {fmt_counts(snap.get('niveis'))}

**Tabela 1 – Indicadores climáticos e ambientais selecionados, Mato Grosso, {semana.get('rotulo', '—')}**

| Indicador | Observado | Unidade | Referência/parâmetro | Cobertura |
| --- | --- | --- | --- | --- |
| Temperatura máxima mediana | {fmt_num(snap.get('tmax_mediana'), 1)} | °C | calor seco se Tmáx ≥ 37 °C (operacional) | {fmt_frac(snap.get('cobertura_tmax'), snap.get('n_municipios'))} |
| Umidade relativa mediana | {fmt_num(snap.get('umidade_mediana'), 0)} | % | UR ≤ 30% (parâmetro operacional ARARAS) | {fmt_frac(snap.get('cobertura_umidade'), snap.get('n_municipios'))} |
| PM2,5 mediano | {fmt_num(snap.get('pm25_mediana'), 1)} | µg/m³ | ≥ 25 µg/m³ = atenção sanitária desta rodada | {fmt_frac(snap.get('cobertura_pm25'), snap.get('n_municipios'))} |
| UTCI proxy mediano | {fmt_num(snap.get('utci_mediana'), 1)} | °C | conforto térmico (proxy) | {fmt_frac(snap.get('n_municipios'), snap.get('n_municipios'))} |

Fonte: ARARAS MT/CIEVS-MT. Rodada {semana.get('gerado_em_pt', '—')}. Data de referência: {ref_data}.

{interpretar_temperatura(snap)}

{interpretar_umidade(snap)}

{interpretar_pm25(snap)}

{analisar_cenario_bloco('Interpretação da situação climática atual', [leitura_integrada(snap)])}

---

## 5. Mato Grosso — Projeção operacional (~7 dias)

A projeção operacional do ARARAS MT estima a classificação municipal para aproximadamente sete dias, permitindo comparação com a situação atual.

Distribuição projetada: {fmt_counts(snap.get('niveis_projecao_7d'))}

---

## 6. Mapa atual × mapa ~7 dias

{mapa_md}

**Legenda:** {NIVEL_LEGENDA.get('verde')} · {NIVEL_LEGENDA.get('amarela')} · {NIVEL_LEGENDA.get('laranja')} · {NIVEL_LEGENDA.get('vermelha')} · {NIVEL_LEGENDA.get('roxa')}

---

## 7. Alertas meteorológicos e ambientais — Mato Grosso

Parâmetro climático oficial para a semana **{semana.get('rotulo', '—')}** ({semana.get('periodo_pt', '—')}).

_Recorte territorial: **Estado de Mato Grosso**. Alertas do INMET listam apenas trechos que abrangem MT; Mato Grosso do Sul (MS) é excluído._

{inmet.get('resumo_climatico_md', INDISPONIVEL)}

### Instituto Nacional de Meteorologia (INMET) — avisos vigentes

{inmet.get('inmet_vigentes_md', INDISPONIVEL)}

Consulta: {inmet.get('consulta_em', '—')}. Fonte: feed Alert-AS / portal INMET {inmet.get('citacao_inmet', cite('inmet_alertas'))}.

### INMET — avisos futuros na semana (previsão oficial)

{inmet.get('inmet_futuros_md', '_Nenhum aviso futuro identificado para o restante da semana._')}

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
- Situação hidro no recorte disponível: {fmt_counts(snap.get('hidro'))}
- Precipitação mediana no **dia de referência operacional**: **{fmt_num(snap.get('precip_mediana'), 1, ' mm')}** · municípios sem chuva nesse dia: {fmt_frac(snap.get('n_sem_chuva'), snap.get('n_municipios'))}

{analisar_cenario_bloco('Limitação dos dados hidrológicos', [
    'Limitação dos dados. A leitura hidrológica desta rodada está restrita aos municípios com observação válida; os resultados não devem ser extrapolados para todo o estado. Sinais hidrológicos locais de baixa disponibilidade não substituem a classificação do Monitor de Secas.',
])}

---

## 9. Fogo e qualidade do ar

{_narrativa(cenario, 'risco_fogo', str(mt.get('risco_fogo') or INDISPONIVEL))}

- {interpretar_fogo(snap)}
- IQA (classes, ordem operacional): {fmt_counts(snap.get('qualidade_ar'), ordem=['verde', 'amarela', 'laranja', 'vermelha', 'roxa', 'cinza'])}
- {interpretar_pm25(snap)}

{analisar_cenario_bloco('Implicações para a saúde — fogo e ar', [
    'A combinação de focos de calor e material particulado fino reforça a vigilância de agravos respiratórios nos municípios prioritários.',
])}

---

## 10. Impactos potenciais à saúde

Associação temporal/espacial — **não implica causalidade**.

{impactos_potenciais_saude()}

### Monitoramento epidemiológico — dados observados

- **Respiratórios/fumaça:** {fmt_frac((agr.get('respiratorio_fumaca') or {}).get('municipios_pm25_25'), snap.get('n_municipios'))} com PM2,5 ≥ 25 µg/m³ em {ref_data}.
- **Calor/desidratação:** {fmt_int((agr.get('calor_desidratacao') or {}).get('municipios_calor_seco'))} municípios em condição combinada de calor seco (Tmáx ≥ 37 °C e UR ≤ 30%).
- **Arboviroses:** {fmt_int((agr.get('arboviroses_contexto_estiagem') or {}).get('casos_arbovirus_7d_soma'))} casos em 7 dias no recorte com dado (ausência não é zero).
- **Hidrorelacionados:** {fmt_int((agr.get('hidrorelacionados') or {}).get('municipios_hidro_alerta'))} municípios com sinal hidrológico de alerta no recorte disponível.

{_secao_agravos_dw(agr)}

{analisar_cenario_bloco('Leitura epidemiológica', [
    'Associação temporal e espacial não implica causalidade. Sinais assistenciais e de notificação devem ser lidos com a defasagem das fontes e com a cobertura de cada indicador.',
])}

---

## 11. Municípios e regionais prioritários

### Regionais de saúde

{tab_reg}

### {secao_mun}

{tab_prior}

### {prontidao.get('titulo', 'Índice de prioridade de preparação clima–saúde')}

{prontidao.get('tabela_md', INDISPONIVEL) if prontidao.get('validado', True) else '_Índice de prioridade de preparação não publicado nesta rodada: inconsistência ou saturação detectada._'}

_{prontidao.get('nota', '')}_

---

## 11b. Síntese territorial da semana

{sintese_territorial(snap)}

---

## 11c. Povos indígenas e comunidades tradicionais em áreas prioritárias

{f'''**Mapa 3 – Classificação de risco climático, aldeias indígenas e municípios com comunidades quilombolas certificadas em Mato Grosso**

![Mapa 3]({maps.get("mapa_territorios")})

Fonte: ARARAS MT/CIEVS-MT, com dados da FUNAI e Fundação Cultural Palmares. Rodada de {semana.get('gerado_em_pt', '—')}.
Nota: para comunidades sem coordenadas geográficas validadas, a representação cartográfica ocorre no nível municipal e não corresponde à localização exata da comunidade. Comunidade certificada não equivale a território titulado.
''' if maps.get('territorio_disponivel') and maps.get('mapa_territorios') else ''}

### Municípios com aldeias indígenas em classes vermelha ou roxa

{territorios.get('quadro_md', INDISPONIVEL)}

_{territorios.get('nota_aldeias', '')}_

### Comunidades quilombolas certificadas em áreas de risco

{territorios.get('quilombo_md', INDISPONIVEL)}

_{territorios.get('nota_quilombos', '')}_

### Populações prioritárias

{populacoes_prioritarias(snap)}

---

## 12. Medidor de trajetória `{SELDERIV}`

{interpretar_medidor(med, snap)}

---

## 13. Orientações operacionais por cenário climático

{orientacoes_por_cenario(snap)}

---

## 14. Preparação assistencial e farmacêutica

Avaliar capacidade e autonomia de insumos da Assistência Farmacêutica (SAF) conforme protocolos oficiais (RENAME, PCDT, notas técnicas MS/SES), orientando redução de exposição conforme protocolos vigentes. **Não prescreve medicamentos.**

### Estoques estratégicos SES — autonomia de insumos

{estoque_saf.get('resumo_md', INDISPONIVEL)}

{estoque_saf.get('tabela_md', '')}

### Matriz clima × saúde × estoque × ação

{matriz_clima_saude_acao(snap)}

---

## Recomendações oficiais aos estados e municípios `{SELSAZ}`

Fonte: Painel El Niño n.º {cenario.get('edicao', '—')} — não são gatilhos automáticos do ARARAS.

{rec_md}

## 15. Matriz de encaminhamentos da semana (áreas da SES-MT)

{matriz_areas_ses(snap)}

### Articulações intersetoriais recomendadas

{articulacao_intersetorial(snap)}

### Saúde do Trabalhador e da Trabalhadora

{saude_trabalhador(snap)}

{pauta}

---

## 16. Notas metodológicas

- **Horizontes:** cenário sazonal (semanas/meses), situação atual (observado), projeção operacional de aproximadamente sete dias (ARARAS).
- **Tratamento de dados ausentes:** valores não disponíveis não são convertidos em zero.
- **Índice de prioridade de preparação:** expressa necessidade de preparação (maior = maior urgência); metodologia na seção correspondente.
- **Figuras e tabelas:** identificação acima e fonte abaixo (NBR 14724 / NBR 10719); referências bibliográficas em NBR 6023.

---

## 17. Glossário

| Termo | Definição |
| --- | --- |
| Anomalia | Diferença entre valor observado e climatologia de referência. |
| Climatologia | Comportamento médio esperado para região e época. |
| PM2,5 | Partículas com diâmetro aerodinâmico até 2,5 µm. |
| Percentil 95 (P95) | Valor acima do qual estão cerca de 5% das observações históricas comparáveis. |
| Índice de prioridade de preparação | Score 0–100 de necessidade de preparação clima–saúde (maior = maior urgência). |
| Índice de prioridade global | Score 0–100 do painel (vigilância, pressão, adaptação, fragilidade, alerta). |

---

{conclusao_tendencia(snap, cenario, inmet)}

## 18. Referências

{chr(10).join(r for r in refs_biblio)}
"""
    return expand_siglas(md)
