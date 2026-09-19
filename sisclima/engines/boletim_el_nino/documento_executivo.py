# -*- coding: utf-8 -*-
"""Boletim executivo (Secretário e gestores) — corpo gerencial + ponteiro ao técnico da Sala.

Ver docs/apresentacoes/DOIS_BOLETINS_PRODUTO.md.
"""
from __future__ import annotations

import re
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
    bloco_tabela,
    fmt_distribuicao_niveis,
    fmt_frac,
    fmt_int,
    fmt_num,
    md_table,
)
from sisclima.engines.boletim_el_nino.plano_acao_rodada import markdown_plano_acao_rodada


def _strip_interno(txt: str) -> str:
    """Remove identificadores técnicos internos do texto público."""
    if not txt:
        return txt
    out = txt
    for pat in (
        r"`?sem_forecast_fresco`?",
        r"`?openmeteo_forecast_7d`?",
        r"`?fonte_predicao`?",
        r"`?FORECAST_[A-Z_]+`?",
        r"\bopenmeteo_forecast\b",
        r"\bsem_forecast_fresco\b",
    ):
        out = re.sub(pat, "", out, flags=re.I)
    out = re.sub(r"[^\S\n]{2,}", " ", out)
    out = re.sub(r" +\n", "\n", out)
    return out.strip()


def _facts(snap: dict[str, Any]) -> dict[str, Any]:
    """Única fonte de verdades numéricas do executivo."""
    rf = dict(snap.get("REPORT_FACTS") or {})
    niveis = rf.get("current_classes") or rf.get("niveis") or snap.get("niveis") or {}
    proj = rf.get("projected_classes") or rf.get("niveis_projecao_7d") or snap.get("niveis_projecao_7d") or {}
    delta = rf.get("delta_projecao") or snap.get("delta_projecao") or {}
    n = int(rf.get("n_municipios") or rf.get("current_total") or snap.get("n_municipios") or 0)
    crit = rf.get("n_vermelha_roxa")
    if crit is None:
        crit = int(niveis.get("vermelha") or 0) + int(niveis.get("roxa") or 0)
    proj_crit = int(proj.get("vermelha") or 0) + int(proj.get("roxa") or 0)
    n_ag = rf.get("n_agravadores")
    if n_ag is None:
        n_ag = int(delta.get("aumento_1") or 0) + int(delta.get("aumento_2plus") or 0)
    picos = snap.get("picos_termicos") or {}
    n37_rodada = rf.get("n_tmax_37_rodada")
    if n37_rodada is None:
        n37_rodada = snap.get("n_tmax_37")
    n37_janela = rf.get("n_tmax_37_janela")
    if n37_janela is None:
        n37_janela = picos.get("n_tmax_37") if picos.get("ok") else snap.get("n_tmax_37_semana")
    pico = rf.get("tmax_max_janela")
    if pico is None:
        pico = picos.get("tmax_max_semana") if picos.get("ok") else snap.get("tmax_max_semana")
    return {
        "n": n,
        "niveis": niveis,
        "proj": proj,
        "delta": delta,
        "crit": int(crit or 0),
        "proj_crit": proj_crit,
        "n_agravadores": int(n_ag or 0),
        "aumento_1": int(delta.get("aumento_1") or 0),
        "aumento_2plus": int(delta.get("aumento_2plus") or 0),
        "estabilidade": int(delta.get("estabilidade") or 0),
        "melhora": int(delta.get("melhora") or 0),
        "n_tmax_37_rodada": int(n37_rodada or 0),
        "n_tmax_37_janela": int(n37_janela or 0) if n37_janela is not None else None,
        "tmax_max_janela": pico,
        "n_umidade_30": snap.get("n_umidade_30"),
        "n_pm25_25": snap.get("n_pm25_25"),
        "focos_7d_total": snap.get("focos_7d_total"),
        "n_com_focos_7d": snap.get("n_com_focos_7d"),
        "umidade_mediana": snap.get("umidade_mediana"),
        "pm25_max": snap.get("pm25_max"),
        "n_tmax_41": picos.get("n_tmax_41") if picos.get("ok") else snap.get("n_tmax_41_semana"),
        "n_tmax_40": picos.get("n_tmax_40") if picos.get("ok") else snap.get("n_tmax_40_semana"),
    }


def _proj_crit(snap: dict[str, Any]) -> int:
    return int(_facts(snap)["proj_crit"])


def _n_agravadores(snap: dict[str, Any]) -> int:
    return int(_facts(snap)["n_agravadores"])


def _aumento_2plus(snap: dict[str, Any]) -> int:
    return int(_facts(snap)["aumento_2plus"])


def _cards_sintese(snap: dict[str, Any], *, rotulo: str = "SE") -> str:
    if not snap.get("disponivel"):
        return INDISPONIVEL
    f = _facts(snap)
    n = f["n"]
    crit = f["crit"]
    proj_crit = f["proj_crit"]
    pct = f"{fmt_num(100.0 * float(crit) / float(n), 1, '%')} do estado" if n else ""
    pico = f["tmax_max_janela"]
    n37j = f["n_tmax_37_janela"]
    n37r = f["n_tmax_37_rodada"]
    calor_linha1 = (
        f"pico da janela observada **{fmt_num(pico, 1, ' °C')}**"
        if pico is not None
        else "pico da janela observada indisponível"
    )
    calor_linha2 = (
        f"hoje/rodada **{fmt_frac(n37r, n)}** ≥ 37 °C · "
        f"janela **{fmt_frac(n37j, n)}** ≥ 37 °C"
    )
    body = f"""| RISCO ATUAL | PROJEÇÃO ~7 DIAS | CALOR |
| --- | --- | --- |
| **{fmt_int(crit)}/{fmt_int(n)}** vermelho ou roxo | **{fmt_int(proj_crit)}/{fmt_int(n)}** vermelho ou roxo | {calor_linha1} |
| {pct} | {fmt_int(f['n_agravadores'])} em agravamento · {fmt_int(f['aumento_2plus'])} com +2 níveis ou mais | {calor_linha2} |

| UMIDADE | FOGO | QUALIDADE DO AR |
| --- | --- | --- |
| **{fmt_frac(f['n_umidade_30'], n)}** ≤ 30% | **{fmt_int(f['focos_7d_total'])}** focos de calor | **{fmt_frac(f['n_pm25_25'], n)}** ≥ 25 µg/m³ |
| mediana {fmt_num(f['umidade_mediana'], 0, '%')} | 7 dias · {fmt_int(f['n_com_focos_7d'])} municípios | máximo {fmt_num(f['pm25_max'], 1, ' µg/m³')} |
"""
    return (
        f"**Quadro 1 – Síntese dos riscos e sinais monitorados na {rotulo}**\n\n"
        f"{body}\n"
        "Fontes: ARARAS MT/CIEVS-MT; Instituto Nacional de Meteorologia (INMET); "
        "Instituto Nacional de Pesquisas Espaciais (INPE)/Programa Queimadas; "
        "Centro Nacional de Monitoramento e Alertas de Desastres Naturais (CEMADEN); "
        "IndicaSUS/SIEGES, conforme respectivas datas de corte da rodada.\n"
    )


def _leitura_sala_executiva(snap: dict[str, Any]) -> str:
    """No máximo 6 mensagens obrigatórias — sem metodologia RIT/EHF."""
    f = _facts(snap)
    n = f["n"]
    msgs = [
        f"**Atual:** {fmt_frac(f['crit'], n)} municípios em vermelho ou roxo.",
        f"**Projeção ~7 dias:** {fmt_frac(f['proj_crit'], n)} em vermelho ou roxo.",
        f"**Agravamento de classe:** {fmt_int(f['n_agravadores'])} de {fmt_int(n)} municípios "
        f"({fmt_int(f['aumento_1'])} +1 nível; {fmt_int(f['aumento_2plus'])} +2 ou mais).",
        f"**Estabilidade / melhora:** {fmt_int(f['estabilidade'])} estáveis · {fmt_int(f['melhora'])} em melhora.",
        "**Principal driver:** térmico (temperatura máxima projetada e persistência de calor).",
    ]
    partes_expo = []
    if f["n_tmax_37_rodada"]:
        partes_expo.append(f"hoje/rodada Tmáx ≥ 37 °C em {fmt_frac(f['n_tmax_37_rodada'], n)}")
    if f["n_tmax_37_janela"]:
        partes_expo.append(f"janela observada ≥ 37 °C em {fmt_frac(f['n_tmax_37_janela'], n)}")
    if f["n_pm25_25"]:
        partes_expo.append(f"PM2,5 ≥ 25 µg/m³ em {fmt_frac(f['n_pm25_25'], n)}")
    if f["focos_7d_total"]:
        partes_expo.append(f"{fmt_int(f['focos_7d_total'])} focos de calor em 7 dias")
    if partes_expo:
        msgs.append("**Exposições/alertas concomitantes:** " + "; ".join(partes_expo) + ".")
    else:
        msgs.append(
            "**Exposições/alertas concomitantes:** sem extremos adicionais destacáveis além do térmico."
        )
    return "\n\n".join(msgs[:6])


def _box_atos_novos(snap: dict[str, Any]) -> str:
    """Somente atos novos/alterados desde a última rodada; lista histórica no anexo."""
    atos = snap.get("atos_novos_rodada") or snap.get("novos_atos_climaticos") or []
    if isinstance(atos, str) and atos.strip():
        return (
            "**Novos atos relevantes desde a última rodada**\n\n"
            f"{atos.strip()}\n"
        )
    if isinstance(atos, list) and atos:
        bullets = "\n".join(f"- {a}" for a in atos[:8])
        return (
            "**Novos atos relevantes desde a última rodada**\n\n"
            f"{bullets}\n"
        )
    return (
        "**Novos atos relevantes desde a última rodada**\n\n"
        "Sem novos atos climáticos relevantes nesta rodada.\n"
    )


def _rit_sintese(snap: dict[str, Any]) -> str:
    rit = snap.get("rit") or {}
    if not rit.get("disponivel"):
        return "_RIT indisponível nesta rodada._"
    n = rit.get("n") or snap.get("n_municipios")
    crit = rit.get("n_critico")
    comp = rit.get("completude_mediana")
    omit = int(rit.get("n_pressao_omitida") or 0)
    n_ar = rit.get("n_ar_dominante")
    n_rede = rit.get("n_rede_dominante")
    n_ar_vr = rit.get("n_ar_vr")
    n_rede_vr = rit.get("n_rede_vr")
    lines = [
        "**RIT (Risco Integrado Territorial)** — leitura observada multidomínio; "
        "**não** equivale à classificação operacional ARARAS enquanto não houver regra "
        "validada de completude mínima.",
        "",
        f"- Faixa vermelha ou roxa no RIT: **{fmt_frac(crit, n)}**.",
        f"- Completude mediana dos domínios: **{fmt_num(comp, 0, '%') if comp is not None else '—'}**.",
    ]
    if n_ar is not None:
        lines.append(
            f"- **Ar/PM2,5** como domínio dominante: **{fmt_frac(n_ar, n)}**"
            + (
                f" (destes em vermelha/roxa: **{fmt_frac(n_ar_vr, n_ar)}**)."
                if n_ar_vr is not None and int(n_ar or 0) > 0
                else "."
            )
        )
    if n_rede is not None:
        lines.append(
            f"- **Fragilidade de rede** (100−IRM) como domínio dominante: **{fmt_frac(n_rede, n)}**"
            + (
                f" (destes em vermelha/roxa: **{fmt_frac(n_rede_vr, n_rede)}**)."
                if n_rede_vr is not None and int(n_rede or 0) > 0
                else "."
            )
            + " IRM alto não eleva o RIT."
        )
    if omit:
        lines.append(
            f"- **Domínio pressão assistencial omitido do RIT por defasagem** em "
            f"**{fmt_int(omit)}** municípios (limite 14 dias) — métrica distinta do "
            "indicador composto pressão × resiliência/IRM (capacidade de rede)."
        )
    lines.append(
        "- Top 10 municipal, quadro por domínio dominante e metodologia: **Anexo técnico**."
    )
    return "\n".join(lines)


def _ehf_sintese(snap: dict[str, Any]) -> str:
    geo = snap.get("geocalor_fiocruz") or {}
    if geo.get("ehf_consistency_error"):
        return (
            "_EHF/GeoCalor: inconsistência entre municípios com dia de onda na janela e "
            "eventos (≥ 3 dias) — publicação detalhada bloqueada até reconciliação "
            "(ver Anexo técnico / QA)._"
        )
    if not geo.get("ok"):
        ref = snap.get("ehf_data_ref")
        n_onda = snap.get("n_onda_geocalor_ativa")
        if ref is None and n_onda is None:
            return "_EHF/GeoCalor indisponível nesta rodada._"
    ref = geo.get("data_referencia_serie") or snap.get("ehf_data_ref") or "—"
    n_last = geo.get("n_mun_onda_ultimo_dia")
    if n_last is None:
        n_last = snap.get("n_onda_geocalor_ativa")
    n_ev_mun = geo.get("n_mun_com_evento_janela")
    n_ev = geo.get("n_eventos_janela")
    lines = [
        f"- **Último dia da série ({ref}):** **{fmt_int(n_last)}** municípios em dia de onda.",
    ]
    if n_ev_mun is not None:
        lines.append(
            f"- **Na janela:** **{fmt_int(n_ev_mun)}** municípios com evento de onda "
            f"(≥ 3 dias consecutivos)"
            + (f" · **{fmt_int(n_ev)}** eventos" if n_ev is not None else "")
            + "."
        )
    lines.append(
        "- Interpretação: monitoramento observado de onda de calor; **não** entra no cálculo "
        "da classe projetada ~7 dias. Tabela detalhada: Anexo técnico."
    )
    return "\n".join(lines)


def _bloco_esus_caixa(agr: dict[str, Any]) -> str:
    dw = agr.get("dw_epidemiologia") or {}
    esus = dw.get("esus_aps") or agr.get("esus_aps") or {}
    if esus.get("status") != "ativo" or int(esus.get("municipios") or 0) <= 0:
        return (
            "> **e-SUS APS — contexto estrutural**\n>\n"
            "> Fonte indisponível ou sem municípios nesta rodada. "
            "Não utilizado como pressão assistencial corrente.\n"
        )
    data_max = esus.get("data_max_atendimento") or "—"
    atraso = int(esus.get("atraso_dias") or 0)
    # Datas legíveis
    data_pt = str(data_max)
    if re.match(r"\d{4}-\d{2}-\d{2}", data_pt):
        y, m, d = data_pt[:10].split("-")
        data_pt = f"{d}/{m}/{y}"
    return (
        "> **e-SUS APS — contexto estrutural**\n>\n"
        f"> Última carga: **{data_pt}**. Defasagem: **{fmt_int(atraso)}** dias. "
        "Não utilizado como pressão assistencial corrente.\n>\n"
        f"> Cadastro (contexto): idosos 60+ **{fmt_int(esus.get('idoso_60mais'))}** · "
        f"gestantes **{fmt_int(esus.get('gestante'))}** · asma **{fmt_int(esus.get('asma'))}**. "
        "Tabelas detalhadas: Anexo técnico.\n"
    )


def _bloco_sim_curto(agr: dict[str, Any]) -> str:
    dw = agr.get("dw_epidemiologia") or {}
    sim = dw.get("sim") or agr.get("sim") or {}
    if not sim:
        return (
            "- **SIM (exploratório):** módulo de mortalidade disponível no Anexo técnico; "
            "não utilizado como gatilho operacional nesta rodada."
        )
    return (
        f"- **SIM (exploratório):** {sim.get('resumo') or 'ver Anexo técnico'} — "
        "não utilizado como gatilho operacional. Metodologia e CID: Anexo técnico."
    )


def _assistencia_e_intersecao(snap: dict[str, Any], *, when: str = "—") -> str:
    lines = ["### Assistência hospitalar e regulação", ""]
    try:
        from sisclima.reporting.quadro_risco_pressao import quadro_risco_pressao

        q = quadro_risco_pressao()
    except Exception:
        q = {"disponivel": False}

    if not q.get("disponivel"):
        lines.append(
            "- Ocupação IndicaSUS e pressão SISREG indisponíveis nesta rodada."
        )
    else:
        lines.append(
            f"- **Ocupação estadual (IndicaSUS):** "
            f"**{q.get('ocupacao_ponderada_txt') or q.get('ocupacao_media_txt') or '—'}%** "
            f"({q.get('leitos_ocupados_txt') or '—'} ocupados / "
            f"{q.get('leitos_total_txt') or '—'} elegíveis)."
        )
        por_reg = [
            r
            for r in (q.get("ocupacao_por_regional") or [])
            if str(r.get("regional") or "").strip() not in {"", "—", "nan", "None"}
            and r.get("ocupacao_ponderada") is not None
        ][:5]
        if por_reg:
            rows = []
            for r in por_reg:
                oc = r.get("ocupacao_ponderada")
                rows.append(
                    [
                        str(r.get("regional") or "—"),
                        f"{oc:.1f}%".replace(".", ","),
                        fmt_int(r.get("n_municipios")),
                    ]
                )
            lines.extend(
                [
                    "",
                    bloco_tabela(
                        "Ocupação hospitalar ponderada por Regional de Saúde",
                        md_table(["Regional", "Ocup. ponderada", "Municípios"], rows),
                        f"IndicaSUS/SIEGES; ARARAS MT/CIEVS-MT, rodada de {when}.",
                    ),
                    "",
                ]
            )
        # Top municípios: só com valor válido (ocupacao_leitos_pct / ocupacao_ponderada)
        top_mun = (q.get("top_ocupacao") or q.get("ranking_ocupacao") or [])[:10]
        rows = []
        for r in top_mun:
            if not isinstance(r, dict):
                continue
            oc = r.get("ocupacao_leitos_pct")
            if oc is None:
                oc = r.get("ocupacao_ponderada")
            if oc is None:
                oc = r.get("ocupacao")
            if oc is None:
                continue
            rows.append(
                [
                    str(r.get("municipio") or "—"),
                    f"{float(oc):.1f}%".replace(".", ","),
                    str(r.get("regional") or "—"),
                ]
            )
        if rows:
            tem_regional = any(r[2] not in ("—", "", "None", "nan") for r in rows[:8])
            if tem_regional:
                tab = md_table(["Município", "Ocupação", "Regional"], rows[:8])
            else:
                tab = md_table(
                    ["Município", "Ocupação"],
                    [[r[0], r[1]] for r in rows[:8]],
                )
            lines.extend(
                [
                    "",
                    bloco_tabela(
                        "Municípios com maior ocupação hospitalar",
                        tab,
                        f"IndicaSUS/SIEGES; ARARAS MT/CIEVS-MT, rodada de {when}.",
                    ),
                    "",
                ]
            )

        carga = (
            q.get("sisreg_carga_em")
            or q.get("sisreg_atualizado_em")
            or q.get("data_carga_sisreg")
            or snap.get("sisreg_carga_em")
        )
        if carga:
            lines.append(
                f"- **SISREG:** solicitações no recorte da carga de **{carga}** — "
                f"**{fmt_int(q.get('sisreg_n'))}** municípios com dado · "
                f"média municipal {q.get('sisreg_solicitacoes_media_txt') or '—'} · "
                f"máximo {q.get('sisreg_solicitacoes_max_txt') or '—'}. "
                "Solicitações = demanda regulada (fila/acumulado conforme carga), não ocupação de leito."
            )
        else:
            lines.append(
                "- **SISREG:** ranking omitido do corpo executivo — temporalidade da carga "
                "não explícita nesta rodada (detalhe no Anexo técnico)."
            )

    lines.extend(
        [
            "",
            "### Convergência climática × assistência",
            "",
            "Municípios em que **agravamento climático projetado** converge com "
            "**ocupação/pressão assistencial válida** e/ou **capacidade local limitada** "
            "devem ser priorizados pela Atenção à Saúde (lista operacional no painel; "
            "sem limiar novo sem validação institucional).",
        ]
    )
    return "\n".join(lines)


def _cenarios_situacao_impacto(snap: dict[str, Any]) -> str:
    """Seca/calor/fumaça/inundação: só situação, impacto, territórios — sem ações."""
    f = _facts(snap)
    n = f["n"]
    lines = ["### Cenários da rodada (situação e impacto)", ""]
    pico_txt = (
        f"pico da janela observada **{fmt_num(f['tmax_max_janela'], 1, ' °C')}**"
        if f["tmax_max_janela"] is not None
        else "pico da janela observada indisponível"
    )
    lines.extend(
        [
            "**Calor**",
            f"- Situação — **hoje/rodada:** {fmt_frac(f['n_tmax_37_rodada'], n)} ≥ 37 °C; "
            f"**janela observada:** {fmt_frac(f['n_tmax_37_janela'], n)} atingiram ≥ 37 °C; "
            f"{pico_txt}.",
            "- Impacto à saúde: risco de desidratação, agravos relacionados ao calor e sobrecarga em vulneráveis.",
            "- Áreas de atenção: municípios vermelho ou roxo e com agravamento projetado.",
            "",
            "**Seca / estiagem**",
            f"- Situação: umidade ≤ 30% em {fmt_frac(f['n_umidade_30'], n)} "
            f"(mediana {fmt_num(f['umidade_mediana'], 0, '%')}).",
            "- Impacto à saúde: agravamento de doenças respiratórias e estresse térmico.",
            "- Áreas de atenção: regionais com maior concentração VR.",
            "",
            "**Fumaça / qualidade do ar**",
            f"- Situação: PM2,5 ≥ 25 µg/m³ em {fmt_frac(f['n_pm25_25'], n)}; "
            f"{fmt_int(f['focos_7d_total'])} focos em 7 dias.",
            "- Impacto à saúde: irritação respiratória, SRAG e agravos cardiorrespiratórios em sensíveis.",
            "- Áreas de atenção: municípios com PM2,5 elevado e/ou focos concomitantes.",
            "",
        ]
    )
    if snap.get("evidencia_inundacao"):
        lines.extend(
            [
                "**Inundação / chuva intensa**",
                "- Situação: sinais hidrológicos com evidência na rodada (ver alertas).",
                "- Impacto à saúde: DDA, leptospirose e interrupção de acesso.",
                "- Áreas de atenção: municípios com alerta hidrológico validado.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "**Inundação**",
                "- Situação: sem evidência municipal suficiente de inundação como gatilho nesta rodada.",
                "- Impacto / áreas: não aplicável como prioridade da semana.",
                "",
            ]
        )
    return "\n".join(lines)


def _bloco_territorio(snap: dict[str, Any], territorios: dict[str, Any], maps: dict[str, Any], *, when: str = "—") -> str:
    lines = ["## 5. Priorização territorial e populações prioritárias", ""]
    regs = sorted(
        [r for r in (snap.get("regionais") or []) if isinstance(r, dict)],
        key=lambda r: int(r.get("n_vermelha_roxa") or 0),
        reverse=True,
    )
    if regs:
        rows = [
            [
                str(r.get("regional") or "—"),
                fmt_int(r.get("n_vermelha_roxa")),
                fmt_int(r.get("n")),
                str(r.get("tendencia_7d") or "—"),
            ]
            for r in regs[:6]
        ]
        lines.extend(
            [
                bloco_tabela(
                    "Regionais de Saúde com maior concentração de municípios nas classes vermelha e roxa",
                    md_table(["Regional", "VR", "Total", "Tendência ~7d"], rows),
                    f"ARARAS MT/CIEVS-MT, rodada de {when}.",
                ),
                "",
            ]
        )
        destaques = []
        for nome in ("Sinop", "Rondonópolis"):
            hit = next((r for r in regs if nome.lower() in str(r.get("regional") or "").lower()), None)
            if hit and int(hit.get("n_vermelha_roxa") or 0) >= 14:
                destaques.append(
                    f"**{hit.get('regional')}:** {fmt_int(hit.get('n_vermelha_roxa'))} municípios "
                    "em vermelho ou roxo."
                )
        import re as _re

        def _n_up(txt: Any) -> int:
            m = _re.search(r"↑\s*(\d+)", str(txt or ""))
            return int(m.group(1)) if m else 0

        if regs:
            up_top = max(regs, key=lambda r: _n_up(r.get("tendencia_7d")))
            n_up = _n_up(up_top.get("tendencia_7d"))
            if n_up > 0:
                reg_nome = str(up_top.get("regional") or "")
                if "pontes" in reg_nome.lower() or n_up >= 9:
                    destaques.append(
                        f"**{reg_nome}:** maior quantidade de municípios com elevação "
                        f"projetada (**{n_up}**), conforme dataset da rodada."
                    )
        if destaques:
            lines.extend(["**Destaques da rodada**", ""] + [f"- {d}" for d in destaques] + [""])

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
                bloco_tabela(
                    "Municípios prioritários da rodada",
                    md_table(["Município", "Classe", "Regional"], rows),
                    f"ARARAS MT/CIEVS-MT, rodada de {when}.",
                    nota="Ordenação operacional da rodada; o índice numérico completo permanece no painel/Anexo técnico.",
                ),
                "",
            ]
        )

    if maps.get("mapa_territorios") or maps.get("mapa3"):
        p = maps.get("mapa_territorios") or maps.get("mapa3")
        lines.extend(
            [
                "**Mapa 2 – Classificação ARARAS e territórios indígenas e quilombolas prioritários em Mato Grosso**",
                "",
                f"![Mapa 2]({p})",
                "",
                f"Fonte: elaboração CIEVS-MT/ARARAS MT, com dados da Fundação Nacional dos Povos Indígenas (FUNAI) "
                f"e da Fundação Cultural Palmares. Rodada de {when}.",
                "",
                "Nota: Aldeias são representadas por coordenadas georreferenciadas disponíveis. "
                "Para comunidades quilombolas sem coordenadas oficiais validadas, a representação "
                "indica presença municipal e não localização exata.",
                "",
            ]
        )

    lines.extend(
        [
            "### Populações indígenas e tradicionais",
            "",
            "- **DSEI/SESAI:** validar continuidade assistencial, transporte, referência e capacidade "
            "de resposta das aldeias em áreas com classe vermelha ou roxa + agravamento projetado + "
            "distância assistencial elevada.",
            "- **FUNAI:** articulação territorial/institucional e apoio ao acesso — sem função de "
            "assistência clínica.",
            "- Listas extensas: painel / Anexo técnico da SE.",
            "",
        ]
    )
    resumo_t = territorios.get("resumo_md") or territorios.get("sintese_md") or ""
    bullets = [ln for ln in resumo_t.splitlines() if ln.strip().startswith("-")][:2]
    if bullets:
        lines.extend(bullets)
    return "\n".join(lines)


def _conclusao(snap: dict[str, Any]) -> str:
    f = _facts(snap)
    return f"""## 7. Conclusão

- Atual: **{fmt_frac(f['crit'], f['n'])}** em vermelho ou roxo.
- Projeção ~7 dias: **{fmt_frac(f['proj_crit'], f['n'])}** em vermelho ou roxo.
- Agravamento de classe: **{fmt_int(f['n_agravadores'])}** municípios ({fmt_int(f['aumento_1'])} +1; {fmt_int(f['aumento_2plus'])} +2 ou mais).
- Estabilidade: **{fmt_int(f['estabilidade'])}** · melhora: **{fmt_int(f['melhora'])}**.
- Driver predominante: **térmico**.
- Ação prioritária 24–48 h: CIEVS consolidar lista única de prioritários, validar determinantes e articular o Plano de ação da rodada.
"""


def _anexo_ponteiro(rotulo: str) -> str:
    return f"""## Anexo técnico

Documento completo da mesma semana: **Anexo técnico da {rotulo}**.

Inclui, entre outros: metodologia completa; RIT (Top 10 e composição); EHF detalhado; Odds Ratio/lags; SIM; e-SUS detalhado; séries históricas; tabelas ampliadas; mapas adicionais; atos normativos completos.
"""


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
    """Template executivo — 8 seções + anexo ponteiro."""
    del publico  # reservado
    maps = maps or {}
    alertas = alertas or {}
    territorios = territorios or {}
    enso = cenario.get("enso") or {}
    mt = cenario.get("mato_grosso") or {}
    br = cenario.get("brasil_aso") or {}
    agr = snap.get("agravos_monitorados") or {}
    f = _facts(snap)
    niveis = f["niveis"]
    proj = f["proj"]
    n = f["n"]
    when = semana.get("gerado_em_pt") or semana.get("gerado_em") or "—"
    rotulo = semana.get("rotulo") or "—"

    if USAR_TITULO_SALA_SITUACAO:
        titulo = TITULO_SALA_SITUACAO
        sub = SUBTITULO_SALA_SITUACAO
    else:
        titulo = TITULO_PRODUTO_ATUAL
        sub = SUBTITULO_INSTITUCIONAL

    refs_list = list(referencias or [])
    refs_txt = "\n\n".join(r.strip() for r in refs_list if str(r).strip()) or (
        "Ver Anexo técnico da mesma semana."
    )

    gloss = (
        "Siglas (primeira ocorrência): "
        "Análise, Resposta e Acompanhamento de Riscos, Agravos e Saúde (ARARAS); "
        "El Niño–Oscilação Sul (ENSO); agosto–setembro–outubro (ASO); "
        "temperatura máxima (Tmáx); "
        "material particulado fino com diâmetro aerodinâmico de até 2,5 micrômetros (PM2,5); "
        "Atenção Primária à Saúde (APS); "
        "Secretaria de Estado de Saúde de Mato Grosso (SES-MT); "
        "Sistema Único de Saúde (SUS); "
        "Instituto Nacional de Pesquisas Espaciais (INPE); "
        "Centro Nacional de Monitoramento e Alertas de Desastres Naturais (CEMADEN); "
        "Centro de Informações Estratégicas em Vigilância em Saúde de Mato Grosso (CIEVS-MT)."
    )

    or_frase = (
        "Análise exploratória identificou associação ecológica entre exposição térmica e "
        "indicadores de pressão; resultados não implicam causalidade e permanecem em validação. "
        "Detalhe (Odds Ratio/lags): Anexo técnico."
    )
    if snap.get("sazonalidade_or_ok") is False and not snap.get("sazonalidade_or_exec_md"):
        or_frase = "Sazonalidade/OR: sem pares suficientes nesta rodada (Anexo técnico)."

    mapa1 = ""
    if maps.get("mapa_atual_projecao"):
        mapa1 = (
            "**Mapa 1 – Classificação ARARAS atual e projeção operacional de aproximadamente "
            "sete dias em Mato Grosso**\n\n"
            f"![Mapa 1]({maps['mapa_atual_projecao']})\n\n"
            f"Fonte: ARARAS MT/CIEVS-MT, rodada de {when}.\n\n"
            "Nota: A classe projetada é térmica (com freio sob tendência de esfriamento). "
            "O RIT é produto paralelo observado e não alimenta esta projeção.\n\n"
            "### Como a classe projetada é calculada\n\n"
            "A projeção operacional (~7 dias) usa score térmico 0–100 (máximo entre intensidade, "
            "UTCI, risco cumulativo e onda P95), com freio se a tendência de Tmáx indicar esfriamento.\n\n"
            "**A. Drivers que entram no modelo:** Tmáx prevista, UTCI previsto, risco cumulativo "
            "de calor e onda P95 no horizonte — sem EHF, fumaça/PM2,5 ou pressão assistencial "
            "como entrada matemática nesta versão."
        )
    else:
        mapa1 = "_Mapa 1 indisponível nesta rodada._"

    md = f"""# {titulo}

**{sub}**

**Semana:** {rotulo} · **Gerado em:** {when}  
**Perfil:** executivo (Secretário e gestores) · **Anexo técnico da {rotulo}** (boletim completo da Sala)

**Base normativa:** Portaria nº 0590/2026/GBSES.

{_box_atos_novos(snap)}

_{gloss}_

---

## 1. Síntese executiva

{_cards_sintese(snap, rotulo=str(rotulo))}

{_leitura_sala_executiva(snap)}

Fonte: ARARAS MT/CIEVS-MT, rodada de {when}.

---

## 2. Situação atual e projeção ~7 dias

- **ENSO / ASO (contexto):** {enso.get('estado') or enso.get('fase') or 'conforme painel oficial'} · {br.get('resumo') or mt.get('resumo') or 'calor e estiagem no radar operacional'}.
- Distribuição atual: {fmt_distribuicao_niveis(niveis)} ({fmt_int(n)} municípios).
- Críticos agora: **{fmt_frac(f['crit'], n)}** vermelho ou roxo.
- Projetado ~7 dias: **{fmt_frac(f['proj_crit'], n)}** vermelho ou roxo ({fmt_distribuicao_niveis(proj)}).
- Agravamento: **{fmt_int(f['n_agravadores'])}** ({fmt_int(f['aumento_1'])} +1 nível; **{fmt_int(f['aumento_2plus'])}** +2 ou mais) · estabilidade **{fmt_int(f['estabilidade'])}** · melhora **{fmt_int(f['melhora'])}**.
- Classe projetada: **térmica** (com freio se tendência de esfriamento). RIT é produto paralelo observado.

{mapa1}

### RIT (síntese)

{_rit_sintese(snap)}

Fonte: classificação ARARAS MT / RIT, rodada de {when}.

---

## 3. Exposições ambientais e alertas oficiais

{_cenarios_situacao_impacto(snap)}

{alertas.get('resumo_climatico_md') or ''}

### EHF / GeoCalor (observado)

{_ehf_sintese(snap)}

### Sazonalidade / associações

{or_frase}

Fonte: alertas oficiais (INMET/CEMADEN) e bases ambientais ARARAS, rodada de {when}.

---

## 4. Repercussões em saúde e assistência

{_bloco_esus_caixa(agr)}

{_bloco_sim_curto(agr)}

{_assistencia_e_intersecao(snap, when=when)}

Fonte: bases operacionais SES-MT / SUS, quando disponíveis e com temporalidade explícita.

---

{_bloco_territorio(snap, territorios, maps, when=when)}

Fonte: painel territorial ARARAS MT / CIEVS-MT.

---

## 6. Plano de ação da rodada

{markdown_plano_acao_rodada(snap, rotulo=str(rotulo))}

---

{_conclusao(snap)}

---

## REFERÊNCIAS

{refs_txt}

---

{_anexo_ponteiro(str(rotulo))}
"""
    from sisclima.engines.boletim_el_nino.formatters import expand_siglas, numerar_tabelas

    md = _strip_interno(md)
    md = (
        md.replace("vermelho/roxo", "vermelho ou roxo")
        .replace("vermelha/roxa", "vermelha ou roxa")
        .replace("vermelhos/roxos", "municípios vermelhos ou roxos")
    )
    md = re.sub(r"`Boletim_ElNino_[^`]+\\.md`", f"Anexo técnico da {rotulo}", md)
    return expand_siglas(numerar_tabelas(md))
