# -*- coding: utf-8 -*-
"""Boletim executivo da Sala — 10 blocos, sem ruído de tabelas longas."""
from __future__ import annotations

from typing import Any

from sisclima.engines.boletim_el_nino.constants import (
    INDISPONIVEL,
    SUBTITULO_SALA_SITUACAO,
    TITULO_SALA_SITUACAO,
    USAR_TITULO_SALA_SITUACAO,
    TITULO_PRODUTO_ATUAL,
    SUBTITULO_INSTITUCIONAL,
)
from sisclima.engines.boletim_el_nino.formatters import (
    fmt_distribuicao_niveis,
    fmt_frac,
    fmt_int,
    fmt_num,
    md_table,
)
from sisclima.engines.boletim_el_nino.acoes_sala import markdown_acoes_sala


def _cards_executivo_picos(snap: dict[str, Any]) -> str:
    """Cartões com pico da semana e contagem ≥41 / ≥37."""
    if not snap.get("disponivel"):
        return INDISPONIVEL
    n = snap.get("n_municipios")
    crit = snap.get("n_vermelha_roxa")
    proj = snap.get("niveis_projecao_7d") or {}
    proj_crit = int(proj.get("vermelha") or 0) + int(proj.get("roxa") or 0)
    picos = snap.get("picos_termicos") or {}
    pico = picos.get("tmax_max_semana") if picos.get("ok") else snap.get("tmax_max_semana")
    n41 = picos.get("n_tmax_41") if picos.get("ok") else snap.get("n_tmax_41_semana")
    n40 = picos.get("n_tmax_40") if picos.get("ok") else snap.get("n_tmax_40_semana")
    n37_sem = picos.get("n_tmax_37") if picos.get("ok") else snap.get("n_tmax_37_semana")
    # Grade do dia (contexto, não misturar com pico)
    ext = (snap.get("extremos") or {}).get("tmax") or {}
    tmax_hoje = ext.get("tmax")
    pct = ""
    if crit is not None and n:
        pct = f"{fmt_num(100.0 * float(crit) / float(n), 1, '%')} do estado"
    calor_linha2 = (
        f"**{fmt_int(n41)}** ≥ 41 °C · **{fmt_int(n40)}** ≥ 40 °C · "
        f"**{fmt_frac(n37_sem, n)}** ≥ 37 °C (janela)"
    )
    if pico is None:
        calor_linha1 = f"máxima grade **{fmt_num(tmax_hoje, 1, ' °C')}**"
        calor_linha2 = f"**{fmt_frac(snap.get('n_tmax_37'), n)}** ≥ 37 °C (hoje)"
    else:
        calor_linha1 = f"pico semana **{fmt_num(pico, 1, ' °C')}**"
    return f"""| RISCO ATUAL | PROJEÇÃO ~7 DIAS | CALOR |
| --- | --- | --- |
| **{fmt_int(crit)}/{fmt_int(n)}** vermelho ou roxo | **{fmt_int(proj_crit)}/{fmt_int(n)}** vermelho ou roxo | {calor_linha1} |
| {pct} | agravamento disseminado | {calor_linha2} |

| UMIDADE | FOGO | QUALIDADE DO AR |
| --- | --- | --- |
| **{fmt_frac(snap.get('n_umidade_30'), n)}** ≤ 30% | **{fmt_int(snap.get('focos_7d_total'))}** focos de calor | **{fmt_frac(snap.get('n_pm25_25'), n)}** ≥ 25 µg/m³ |
| mediana {fmt_num(snap.get('umidade_mediana'), 0, '%')} | 7 dias · {fmt_int(snap.get('n_com_focos_7d'))} municípios | máximo {fmt_num(snap.get('pm25_max'), 1, ' µg/m³')} |
"""


def _leitura_curta(snap: dict[str, Any]) -> str:
    from sisclima.engines.boletim_el_nino.documento import _leitura_executiva

    txt = _leitura_executiva(snap)
    return (
        txt.replace("vermelhos/roxos", "municípios vermelhos ou roxos")
        .replace("vermelho/roxo", "vermelho ou roxo")
        .replace("vermelha/roxa", "vermelha ou roxa")
    )


def _bloco_esus_executivo(agr: dict[str, Any], maps: dict[str, Any]) -> str:
    dw = agr.get("dw_epidemiologia") or {}
    esus = dw.get("esus_aps") or agr.get("esus_aps") or {}
    if esus.get("status") != "ativo" or int(esus.get("municipios") or 0) <= 0:
        return ""
    neb7 = int(esus.get("nebulizacao_7d") or 0)
    neb28 = int(esus.get("nebulizacao_28d") or 0)
    show_neb = neb7 > 0 or neb28 > 0

    lines = [
        "## 7. Atenção primária (e-SUS APS) — sinais úteis",
        "",
        f"- Cadastro: **{fmt_int(esus.get('cadastros'))}** · asma **{fmt_int(esus.get('asma'))}** · "
        f"idosos 60+ **{fmt_int(esus.get('idoso_60mais'))}** · gestantes **{fmt_int(esus.get('gestante'))}** · "
        f"acamados **{fmt_int(esus.get('acamado'))}**.",
        f"- Atendimentos: **{fmt_int(esus.get('atendimentos_7d'))}** (7d) · "
        f"**{fmt_int(esus.get('atendimentos_28d'))}** (28d) · "
        f"CID respiratório 28d **{fmt_int(esus.get('resp_cid_28d'))}**.",
    ]
    if show_neb:
        lines.append(
            f"- Nebulização: **{fmt_int(neb28)}** (28d) · **{fmt_int(neb7)}** (7d)."
        )
    atraso = int(esus.get("atraso_dias") or 0)
    if atraso > 0 or esus.get("janela_ancorada"):
        lines.append(
            f"- Atualidade: última data **{esus.get('data_max_atendimento') or '—'}** "
            f"(atraso **{fmt_int(atraso)}** dia(s)). Ausência ≠ zero clínico."
        )
    if maps.get("grafico_esus_vulneraveis"):
        lines.extend(
            [
                "",
                f"![Vulneráveis APS por classe]({maps['grafico_esus_vulneraveis']})",
                "",
                "_Cadastro de idosos/gestantes por classe ARARAS (substitui tabela municipal)._",
            ]
        )
    # Tabela por classe (sem nebulização se zero)
    class_rows = []
    for r in esus.get("por_classe") or []:
        if not isinstance(r, dict):
            continue
        row = [
            str(r.get("classe") or "—"),
            fmt_int(r.get("municipios")),
            fmt_int(r.get("asma")),
            fmt_int(r.get("idoso_60mais")),
            fmt_int(r.get("atendimentos_28d")),
        ]
        if show_neb:
            row.append(fmt_int(r.get("nebulizacao_28d")))
        class_rows.append(row)
    if class_rows:
        headers = ["Classe", "Municípios", "Asma", "Idoso 60+", "Atend. 28d"]
        if show_neb:
            headers.append("Nebuliz. 28d")
        lines.extend(["", md_table(headers, class_rows), ""])
    # Top críticos (máx. 12) só se houver sinal
    mun_src = esus.get("ranking_criticos") or []
    mun_rows = []
    for r in mun_src[:12]:
        if not isinstance(r, dict):
            continue
        sinal = int(r.get("resp_cid_28d") or 0) + int(r.get("atendimentos_28d") or 0)
        if sinal <= 0 and int(r.get("asma") or 0) <= 0:
            continue
        mun_rows.append(
            [
                str(r.get("municipio") or "—"),
                str(r.get("classe_araras") or "—"),
                fmt_int(r.get("asma")),
                fmt_int(r.get("atendimentos_28d")),
                fmt_int(r.get("resp_cid_28d")),
            ]
        )
    if mun_rows:
        lines.extend(
            [
                "",
                "**Top municípios com sinal APS (máx. 12)**",
                "",
                md_table(
                    ["Município", "Classe", "Asma", "Atend. 28d", "CID resp. 28d"],
                    mun_rows[:12],
                ),
                "",
            ]
        )
    return "\n".join(lines)


def _bloco_picos(snap: dict[str, Any], maps: dict[str, Any]) -> str:
    picos = snap.get("picos_termicos") or {}
    lines = ["## 5. Picos térmicos ≥ 41 °C e chuva de 01/09", ""]
    if not picos.get("ok"):
        lines.append("_Histórico municipal diário indisponível para picos da semana nesta rodada._")
        return "\n".join(lines)
    ini = picos.get("janela_inicio") or "—"
    fim = picos.get("janela_fim") or "—"
    n41 = picos.get("n_tmax_41")
    n37 = picos.get("n_tmax_37")
    n_mun = picos.get("n_municipios_janela")
    lines.append(
        f"- Janela **{ini}** a **{fim}**: pico estadual **{fmt_num(picos.get('tmax_max_semana'), 1, ' °C')}** · "
        f"**{fmt_frac(n41, n_mun)}** com Tmáx ≥ 41 °C · **{fmt_frac(picos.get('n_tmax_40'), n_mun)}** ≥ 40 °C · "
        f"**{fmt_frac(n37, n_mun)}** ≥ 37 °C."
    )
    # Grade do dia vs pico
    ext = (snap.get("extremos") or {}).get("tmax") or {}
    if ext.get("tmax") is not None:
        lines.append(
            f"- Contexto da grade do dia (rodada): Tmáx máx. **{fmt_num(ext.get('tmax'), 1, ' °C')}** "
            f"em {ext.get('municipio') or '—'} — distinto do pico da janela."
        )
    # INMET Cuiabá (maps)
    inmet_30 = maps.get("cuiaba_inmet_30ago")
    inmet_31 = maps.get("cuiaba_inmet_31ago")
    om = maps.get("cuiaba_openmeteo_tmax_semana")
    cui_g = picos.get("cuiaba_grade") or {}
    if inmet_30 or inmet_31:
        lines.append(
            f"- **Cuiabá (Instituto Nacional de Meteorologia — INMET):** **{fmt_num(inmet_30, 1, ' °C')}** (30/08) e "
            f"**{fmt_num(inmet_31, 1, ' °C')}** (31/08)"
            + (
                f"; grade Open-Meteo na janela **{fmt_num(cui_g.get('tmax_max') or om, 1, ' °C')}** "
                "(não inventar valor de estação)."
                if (cui_g.get("tmax_max") is not None or om is not None)
                else "."
            )
        )
    ranking = picos.get("ranking_40") or picos.get("ranking_41") or []
    if not ranking:
        lines.append("- Nenhum município com pico ≥ 40 °C nesta janela; ranking ≥ 37 °C abaixo.")
        ranking = picos.get("ranking_37") or []
    if maps.get("grafico_picos_tmax"):
        lines.extend(
            [
                "",
                f"![Picos de Tmáx]({maps['grafico_picos_tmax']})",
                "",
            ]
        )
    if ranking:
        rows = [
            [
                str(r.get("municipio") or "—"),
                fmt_num(r.get("tmax_max"), 1, " °C"),
                str(r.get("data_pico") or "—"),
            ]
            for r in ranking[:10]
        ]
        lines.extend(
            [
                md_table(["Município", "Tmáx pico", "Data"], rows),
                "",
            ]
        )
    chuva_md = str(snap.get("impacto_chuva_md") or "").strip()
    if chuva_md:
        # só bullets curtos — pegar primeiras linhas não-tabela
        short = []
        for ln in chuva_md.splitlines():
            if ln.startswith("|") or ln.startswith("#"):
                continue
            if ln.strip().startswith("-") or ln.strip().startswith("**"):
                short.append(ln)
            if len(short) >= 4:
                break
        if short:
            lines.append("**Impacto da chuva (01/09):**")
            lines.extend(short)
    return "\n".join(lines)


def _bloco_territorios(snap: dict[str, Any], territorios: dict[str, Any]) -> str:
    lines = ["## 8. Territórios prioritários", ""]
    regs = sorted(
        [r for r in (snap.get("regionais") or []) if isinstance(r, dict)],
        key=lambda r: int(r.get("n_vermelha_roxa") or 0),
        reverse=True,
    )[:5]
    if regs:
        rows = [
            [
                str(r.get("regional") or "—"),
                fmt_int(r.get("n_vermelha_roxa")),
                fmt_int(r.get("n")),
            ]
            for r in regs
        ]
        lines.extend(
            [
                "**Top regionais (vermelho/roxo)**",
                "",
                md_table(["Regional", "VR", "Total"], rows),
                "",
            ]
        )
    top = (snap.get("prioritarios") or [])[:8]
    if top:
        rows = [
            [
                str(r.get("municipio") or "—"),
                str(r.get("nivel") or "—"),
                str(r.get("regional_saude") or "—"),
            ]
            for r in top
            if isinstance(r, dict)
        ]
        lines.extend(
            [
                "**Top municípios prioritários**",
                "",
                md_table(["Município", "Classe", "Regional"], rows),
                "",
            ]
        )
    # Povos — 2 bullets
    resumo_t = territorios.get("resumo_md") or territorios.get("sintese_md") or ""
    if not resumo_t:
        cont = territorios.get("contagens") or {}
        if cont:
            lines.append(
                f"- Povos tradicionais em municípios críticos: aldeias/comunidades conforme painel "
                f"({fmt_int(cont.get('aldeias') or cont.get('n_aldeias'))} aldeias · "
                f"{fmt_int(cont.get('quilombos') or cont.get('n_quilombos'))} quilombos — quando disponível)."
            )
        else:
            lines.append(
                "- Priorizar articulação com a Secretaria de Saúde Indígena (SESAI) / Distritos Sanitários "
                "Especiais Indígenas (DSEI) e coordenação quilombola nos municípios vermelhos ou roxos "
                "(detalhe no boletim técnico / Mapa 3)."
            )
    else:
        bullets = [ln for ln in resumo_t.splitlines() if ln.strip().startswith("-")][:2]
        if bullets:
            lines.extend(bullets)
        else:
            lines.append("- Ver boletim técnico para camada de povos tradicionais.")
    lines.append(
        "- Detalhamento cartográfico completo (Mapas 2–3) permanece no anexo técnico."
    )
    return "\n".join(lines)


def format_markdown_executivo(
    cenario: dict[str, Any],
    semana: dict[str, Any],
    snap: dict[str, Any],
    *,
    alertas: dict[str, Any] | None = None,
    maps: dict[str, Any] | None = None,
    territorios: dict[str, Any] | None = None,
    referencias: list[str] | None = None,
    publico: bool = False,
) -> str:
    """Template executivo — 10 blocos."""
    maps = maps or {}
    alertas = alertas or {}
    territorios = territorios or {}
    enso = cenario.get("enso") or {}
    mt = cenario.get("mato_grosso") or {}
    br = cenario.get("brasil_aso") or {}
    agr = snap.get("agravos_monitorados") or {}
    niveis = snap.get("niveis") or {}
    proj = snap.get("niveis_projecao_7d") or {}
    n = snap.get("n_municipios")
    when = semana.get("gerado_em_pt") or semana.get("gerado_em") or "—"
    rotulo = semana.get("rotulo") or "—"

    if USAR_TITULO_SALA_SITUACAO:
        titulo = TITULO_SALA_SITUACAO
        sub = SUBTITULO_SALA_SITUACAO
    else:
        titulo = TITULO_PRODUTO_ATUAL
        sub = SUBTITULO_INSTITUCIONAL

    # §6 impactos — sinais úteis curtos
    impactos: list[str] = []
    dw = agr.get("dw_epidemiologia") or {}
    if dw and dw.get("status") != "indisponivel":
        intox = dw.get("intoxicacao_fumaca") or {}
        intern = dw.get("internacao_indicasus") or dw.get("internacao_hospitalar") or {}
        if intox:
            impactos.append(
                f"- Intoxicação/fumaça (janela): **{fmt_int(intox.get('notificacoes_fumaca_7d'))}** "
                f"com sinal de fumaça / **{fmt_int(intox.get('notificacoes_intox_total_7d'))}** total."
            )
        grupos = intern.get("grupos_7d") or {}
        if intern.get("internacoes_total_7d") is not None:
            impactos.append(
                f"- Internações IndicaSUS (7d): **{fmt_int(intern.get('internacoes_total_7d'))}** · "
                f"resp./alérgico **{fmt_int(grupos.get('resp_alergico'))}** · "
                f"desidratação/calor **{fmt_int(grupos.get('desidratacao_calor'))}**."
            )
    if snap.get("n_pm25_25"):
        impactos.append(
            f"- Qualidade do ar: **{fmt_frac(snap.get('n_pm25_25'), n)}** com PM2,5 ≥ 25 µg/m³."
        )
    if not impactos:
        impactos.append("- Sem sinais epidemiológicos adicionais destacáveis nesta versão executiva.")

    esus_sec = _bloco_esus_executivo(agr, maps)
    if not esus_sec:
        esus_sec = (
            "## 7. Atenção primária (e-SUS APS)\n\n"
            "_Sem sinal agregável nesta rodada (fonte indisponível ou sem municípios)._"
        )

    refs_txt = "\n".join(f"- {r}" for r in (referencias or [])[:8]) or "- Ver boletim técnico completo."

    det_md = ""  # corpo longo do quadro de determinantes fica no anexo técnico
    # (evita **Tabela – sem numeração no QA do executivo)

    gloss = (
        "Siglas (primeira ocorrência): "
        "Análise, Resposta e Acompanhamento de Riscos, Agravos e Saúde (ARARAS); "
        "Análise, Resposta e Acompanhamento de Riscos, Agravos e Saúde (ARARAS MT); "
        "El Niño–Oscilação Sul (ENSO); agosto–setembro–outubro (ASO); "
        "temperatura máxima (Tmáx); "
        "material particulado fino com diâmetro aerodinâmico de até 2,5 micrômetros (PM2,5); "
        "*Universal Thermal Climate Index* (UTCI); "
        "Atenção Primária à Saúde (APS); "
        "Secretaria de Estado de Saúde de Mato Grosso (SES-MT); "
        "Sistema Único de Saúde (SUS); "
        "Instituto Nacional de Pesquisas Espaciais (INPE); "
        "Centro Nacional de Monitoramento e Alertas de Desastres Naturais (CEMADEN)."
    )

    md = f"""# {titulo}

**{sub}**

**Semana:** {rotulo} · **Gerado em:** {when}  
**Perfil:** executivo (Sala de Situação) · anexo técnico: `Boletim_ElNino_{str(rotulo).replace(' ', '_').replace('/', '-')}.md`

_{gloss}_

---

## 1. Cartões e leitura

{_cards_executivo_picos(snap)}

{_leitura_curta(snap)}

Fonte: ARARAS MT/CIEVS-MT, rodada de {when}.

---

## 2. Cenário El Niño / ASO

- **ENSO:** {enso.get('estado') or enso.get('fase') or '—'} · probabilidade / nota: {enso.get('resumo') or enso.get('nota') or 'conforme painel oficial'}.
- **Brasil (ASO):** {br.get('resumo') or br.get('tendencia') or mt.get('contexto_nacional') or '—'}.
- **Mato Grosso:** {mt.get('resumo') or mt.get('tendencia') or mt.get('nota') or 'calor e estiagem no radar operacional da rodada'}.

Fonte: painel oficial El Niño / INPE e consolidação SES-MT.

---

## 3. Situação observada

- Distribuição: {fmt_distribuicao_niveis(niveis)} ({fmt_int(n)} municípios).
- Críticos agora: **{fmt_frac(snap.get('n_vermelha_roxa'), n)}** vermelho ou roxo.

{f"![Classes ARARAS]({maps['grafico_classes']})" if maps.get("grafico_classes") else ""}

Fonte: classificação ARARAS MT, rodada de {when}.

---

## 4. Projeção ~7 dias

- Projetado: **{fmt_frac(int(proj.get('vermelha') or 0) + int(proj.get('roxa') or 0), n)}** vermelho ou roxo
  ({fmt_distribuicao_niveis(proj)}).

{f"![Projeção 7d]({maps['grafico_projecao_7d']})" if maps.get("grafico_projecao_7d") else ""}

{f"![Mapa atual × projeção]({maps['mapa_atual_projecao']})" if maps.get("mapa_atual_projecao") else "_Mapa 1 indisponível nesta rodada._"}

_Mapa 1 — classes atuais e projeção ~7 dias (único mapa obrigatório desta versão)._

Fonte: ARARAS MT — Mapa 1 (atual × projeção operacional ~7 dias), rodada de {when}.

### Determinantes do agravamento projetado

**Como a classe projetada é calculada.** A classe ~7 dias combina a classe atual com a tendência do modelo de risco térmico/ambiental municipal (janela de previsão). Não é um alerta meteorológico pontual.

**Drivers que entram no modelo.** Principais drivers: temperatura máxima projetada, UTCI-proxy, umidade, material particulado e acumulado de risco térmico; a regra de estágio eleva ou mantém a classe conforme limiares operacionais.

{det_md or "_Resumo dos determinantes consolidado no painel; detalhe no anexo técnico._"}

---

{_bloco_picos(snap, maps)}

Fonte: histórico municipal diário ARARAS + Instituto Nacional de Meteorologia (INMET) para Cuiabá (estações), rodada de {when}.

---

## 6. Impactos à saúde (sinais)

{chr(10).join(impactos)}

{alertas.get('resumo_climatico_md') or ''}

Fonte: bases operacionais SES-MT / Sistema Único de Saúde (SUS) e alertas oficiais (INMET/CEMADEN), quando disponíveis.

---

{esus_sec}

Fonte: Centralizador PEC/eSUS (Atenção Primária à Saúde — APS), cruzado com classe ARARAS.

---

{_bloco_territorios(snap, territorios)}

Fonte: painel territorial ARARAS MT / CIEVS-MT.

---

## 9. Recomendações e ações (áreas + implantação Plano)

{markdown_acoes_sala(snap)}

Fonte: orientações por cenário + artefatos de cobrança do Plano El Niño (Portaria SES-MT nº 0590/2026/GBSES).

---

## 10. Limitações e anexo técnico

- Base normativa: Portaria SES-MT nº **0590/2026/GBSES** (Plano El Niño).
- Versão executiva omite tabelas municipais longas, séries históricas, Mapas 2–3, estoques vazios e correlações sem sinal.
- Ocupação hospitalar estadual não é inventada; pressão SISREG ≠ taxa de ocupação IndicaSUS.
- Evidência de indicadores do Plano El Niño: **Sim + SEI** no painel — e-mail sozinho não fecha.
- Instituto Nacional de Meteorologia (INMET) e demais fontes: detalhe no anexo técnico.
- Documento completo (metodologia e anexos): ver MD técnico da mesma SE em `docs/apresentacoes/`.

### Referências (seleção)

{refs_txt}
"""
    return (
        md.replace("vermelho/roxo", "vermelho ou roxo")
        .replace("vermelha/roxa", "vermelha ou roxa")
        .replace("vermelhos/roxos", "municípios vermelhos ou roxos")
    )
