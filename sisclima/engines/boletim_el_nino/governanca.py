# -*- coding: utf-8 -*-
"""Governança SES-MT, Saúde do Trabalhador, encaminhamentos e conclusão."""
from __future__ import annotations

from typing import Any

from sisclima.engines.boletim_el_nino.constants import FOGO_SATELITE_REFERENCIA_CURTO, INDISPONIVEL, UNIEVS_NOME_OFICIAL
from sisclima.engines.boletim_el_nino.formatters import fmt_frac, fmt_int, fmt_num, fmt_pareamento, md_table
from sisclima.engines.boletim_el_nino.referencias import cite


def box_base_normativa() -> str:
    return f"""**Base normativa:** Portaria n.º 0590/2026/GBSES, que institui a Sala de Situação em Saúde para preparação, monitoramento e resposta aos impactos do El Niño 2026–2027 e de eventos climáticos extremos no âmbito da Secretaria de Estado de Saúde de Mato Grosso {cite("portaria_sala_590")}.
"""


def matriz_areas_ses(snap: dict[str, Any]) -> str:
    if not snap.get("disponivel"):
        return INDISPONIVEL
    n = snap.get("n_municipios")
    crit = snap.get("n_vermelha_roxa")
    n25 = snap.get("n_pm25_25")
    blocks = [
        (
            UNIEVS_NOME_OFICIAL,
            "Convergência de calor, fumaça e classes vermelha e roxa",
            "Integrar o cenário, avaliar o risco e comunicar eventos à Sala de Situação.",
            "Estado",
            "Imediato",
        ),
        (
            "Vigilância Epidemiológica",
            "Agravos respiratórios e relacionados ao calor",
            "Monitorar SRAG, DDA e sinais de desidratação no recorte prioritário.",
            "Regionais com maior Tmáx/PM2,5",
            "Até a próxima Sala",
        ),
        (
            "Atenção à Saúde",
            (
                f"Atual: {fmt_frac(crit, n)}; projeção ~7 dias: "
                f"{fmt_frac(int((snap.get('niveis_projecao_7d') or {}).get('vermelha') or 0) + int((snap.get('niveis_projecao_7d') or {}).get('roxa') or 0), n)}"
                if crit is not None and n
                else "Risco climático"
            ),
            "Organizar APS e continuidade do cuidado a grupos vulnerabilizados.",
            "Municípios prioritários",
            "Curto prazo",
        ),
        (
            "Assistência Farmacêutica",
            "Autonomia de insumos críticos na base de Assistência Farmacêutica",
            "Conferir a autonomia dos itens com cálculo válido e validar a situação no sistema oficial de estoques.",
            "Municípios da base operacional, quando houver carga",
            "Imediato",
        ),
        (
            "Gestão Regional",
            (
                f"Atual: {fmt_frac(crit, n)}; agravamento projetado conforme delta ~7 dias"
                if crit is not None and n
                else "Regionais com maior concentração de classes vermelha e roxa"
            ),
            "Contatar municípios prioritários da seção territorial.",
            "Regionais listadas",
            "24/48 h",
        ),
        (
            "Vigilância em Saúde Ambiental / Vigidesastres",
            f"PM2,5 ≥ 25 µg/m³ em {fmt_int(n25)} municípios" if n25 is not None else "Qualidade do ar",
            "Acompanhar fumaça, água e articulações territoriais; considerar projeção de risco térmico integrado.",
            "Municípios nas classes vermelha e roxa (atual e projetada)",
            "Imediato",
        ),
        (
            "Vigilância em Saúde do Trabalhador",
            "Trabalhadores externos urbanos e rurais em calor e fumaça",
            "Orientar ações de vigilância e proteção aos grupos ocupacionais potencialmente expostos.",
            "Estado",
            "Curto prazo",
        ),
        (
            "Comunicação",
            "Cenário de calor e fumaça",
            "Alinhar mensagens de risco à população, sem antecipar decisão de gestão.",
            "Estado",
            "Imediato",
        ),
    ]
    linhas = []
    for area, evid, acao, terr, prazo in blocks:
        linhas.append(
            f"**{area}** — território: {terr} · prazo: {prazo}\n"
            f"- Ação: {acao}\n"
            f"- Evidência: {evid}\n"
        )
    return "\n".join(linhas)


def articulacao_intersetorial(snap: dict[str, Any]) -> str:
    n25 = snap.get("n_pm25_25")
    focos = snap.get("focos_7d_total")
    crit = snap.get("n_vermelha_roxa")
    n = snap.get("n_municipios")
    delta = snap.get("delta_projecao") or {}
    n_d = snap.get("delta_n_comparavel") or n
    n_up = int(delta.get("aumento_1") or 0) + int(delta.get("aumento_2plus") or 0)
    proj = snap.get("niveis_projecao_7d") or {}
    proj_crit = int(proj.get("vermelha") or 0) + int(proj.get("roxa") or 0)
    linhas = [
        "- **SEMA-MT** — compartilhar o cenário de qualidade do ar, focos de calor e territórios prioritários para avaliação ambiental integrada"
        + (f" (PM2,5 elevado em {fmt_int(n25)} municípios)" if n25 else "")
        + ".",
        "- **Defesa Civil Estadual** — compartilhar municípios classificados em níveis elevados e a projeção para os próximos sete dias.",
        "- **Corpo de Bombeiros Militar** — articular informações sobre incêndios florestais nos territórios prioritários"
        + (
            f" (acumulado de {fmt_int(focos)} focos no {FOGO_SATELITE_REFERENCIA_CURTO} em sete dias"
            + (
                f"; {fmt_int(snap.get('deteccoes_7d_total'))} detecções multi-satélite"
                if snap.get("deteccoes_7d_total") is not None
                else ""
            )
            + ")"
            if focos
            else ""
        )
        + ".",
        "- **COSEMS-MT / municípios** — pactuar acompanhamento dos planos de ação nos municípios estratégicos.",
        "- **DSEI / SESAI e FUNAI** — articular continuidade do cuidado em territórios indígenas com risco climático elevado.",
        "- **INMET / CEMADEN / INPE / ANA / SGB** — utilizar apenas produtos oficiais já consultados nesta rodada.",
    ]
    return "\n".join(linhas)


def saude_trabalhador(snap: dict[str, Any]) -> str:
    return """O Ministério da Saúde reconhece trabalhadores externos urbanos e rurais como particularmente expostos a ondas de calor e eventos climáticos extremos.

> **Limitação:** o boletim ainda não dispõe de estimativa do número de trabalhadores potencialmente expostos.

**Exposições ocupacionais coerentes com o cenário da semana:** calor, radiação solar, fumaça, PM2,5, incêndios e esforço físico ao ar livre. Baixa umidade permanece como risco sazonal a acompanhar.

**Grupos ocupacionais a considerar:** trabalhadores rurais e da construção; serviços urbanos externos; coleta de resíduos e saneamento; transporte e entregadores; agentes comunitários e de endemias; brigadistas, bombeiros e Defesa Civil; equipes de unidades de saúde e ambientais.

**Orientação técnica:** CEREST e VISAT monitoram agravos e orientam setores; Gestão de Pessoas revisa proteção das equipes da SES-MT. Encaminhamento administrativo consta na seção 15.
"""


def populacoes_prioritarias(snap: dict[str, Any]) -> str:
    return """**Vulnerabilidade clínica.** Crianças, idosos, gestantes, puérperas e pessoas com doenças crônicas.
- APS: hidratação, sinais de alerta e busca ativa.
- Urgência: fluxos para desidratação, insolação e agravamento respiratório.

**Exposição ocupacional.** Trabalhadores externos, rurais, da construção, saneamento, brigadistas e equipes de campo.
- Centro de Referência em Saúde do Trabalhador (CEREST) e Vigilância em Saúde do Trabalhador (VISAT): orientar setores e monitorar agravos.
- Gestão de pessoas da SES-MT: proteger equipes próprias em campo.

**Vulnerabilidade territorial.** Povos indígenas, comunidades quilombolas e populações do campo, floresta e águas.
- Articular DSEI/SESAI, SMS e organizações locais.
- Priorizar territórios já classificados em vermelho ou roxo.

**Vulnerabilidade social e institucional.** Pessoas com deficiência, população em situação de rua e pessoas privadas de liberdade.
- Articular assistência social, rede municipal e sistema prisional.
- Manter continuidade do cuidado mesmo sem quantitativo nesta rodada.
"""


def sintese_territorial(snap: dict[str, Any]) -> str:
    if not snap.get("disponivel"):
        return INDISPONIVEL
    regs = snap.get("regionais") or []
    top_reg = ", ".join(str(r.get("regional")) for r in regs[:5]) or INDISPONIVEL
    ext = snap.get("extremos") or {}
    delta = snap.get("delta_projecao") or {}
    n_d = snap.get("delta_n_comparavel") or snap.get("n_municipios")
    n_melhora = int(delta.get("melhora") or 0) if delta else None
    if n_melhora == 0:
        melhora_txt = "Não há municípios com melhora projetada nesta rodada."
    elif delta:
        melhora_txt = f"Melhora projetada: {fmt_frac(delta.get('melhora'), n_d)}."
    else:
        melhora_txt = INDISPONIVEL
    ext_pm = (ext.get("pm25") or {})
    ext_focos = (ext.get("focos") or {})
    pm_val = ext_pm.get("pm25_ugm3") or ext_pm.get("pm25")
    focos_val = ext_focos.get("focos_queimadas_7d")
    pm_txt = (
        f" — {fmt_num(pm_val, 1, ' µg/m³')}."
        if pm_val is not None
        else "."
    )
    focos_txt = (
        f" — {fmt_int(focos_val)} focos."
        if focos_val is not None
        else "."
    )
    return f"""- Regionais com maior concentração nas classes vermelha e roxa: **{top_reg}**.
- Maior Tmáx municipal: **{(ext.get('tmax') or {}).get('municipio') or '—'}** ({fmt_num((ext.get('tmax') or {}).get('tmax'), 1, ' °C')}).
- Maior PM2,5 municipal: **{ext_pm.get('municipio') or '—'}**{pm_txt}
- Maior acumulado no satélite de referência: **{ext_focos.get('municipio') or '—'}**{focos_txt}
- Persistência: estabilidade de classe em {fmt_frac(delta.get('estabilidade'), n_d) if delta else INDISPONIVEL}.
- {melhora_txt}
- Limitação dos dados. Cobertura hidrológica: {fmt_frac(snap.get('cobertura_hidro'), snap.get('n_municipios'))}.
"""


def _quadro_encaminhamento(titulo: str, itens: list[tuple[str, str, str, str, str]]) -> str:
    blocos = [f"### {titulo}", ""]
    for resp, terr, acao, evid, prazo in itens:
        blocos.append(f"**{resp}**")
        blocos.append(f"- Território: {terr}")
        blocos.append(f"- Ação: {acao}")
        blocos.append(f"- Evidência: {evid}")
        blocos.append(f"- Prazo: {prazo}")
        blocos.append("")
    return "\n".join(blocos)


def encaminhamentos(snap: dict[str, Any], *, publico: bool) -> str:
    if publico:
        return ""
    n = snap.get("n_municipios")
    crit = snap.get("n_vermelha_roxa")
    delta = snap.get("delta_projecao") or {}
    n_d = snap.get("delta_n_comparavel") or n
    n_up = int(delta.get("aumento_1") or 0) + int(delta.get("aumento_2plus") or 0)
    proj = snap.get("niveis_projecao_7d") or {}
    proj_crit = int(proj.get("vermelha") or 0) + int(proj.get("roxa") or 0)
    evid_transversal = (
        f"Evidência transversal desta rodada: situação atual {fmt_frac(crit, n)} nas classes vermelha e roxa; "
        f"projeção {fmt_frac(proj_crit, n)}; {fmt_frac(n_up, n_d)} em agravamento."
        if crit is not None and n and proj_crit
        else "Classificação elevada e projeção operacional."
    )
    hf = snap.get("hydro_facts") or {}
    n_flood = int(hf.get("flood_risk_high") or 0)
    im = [
        (
            UNIEVS_NOME_OFICIAL,
            "Estado / municípios prioritários",
            "Validar a priorização territorial e consolidar o cenário para a Sala de Situação.",
            "Priorização territorial desta rodada.",
            "24–48 h",
        ),
        (
            "Atenção à Saúde",
            "Municípios prioritários",
            "Avaliar capacidade assistencial e necessidade de contingenciamento conforme evolução da demanda.",
            "Carga assistencial nos municípios em vermelho e roxo.",
            "24–48 h",
        ),
        (
            "Assistência Farmacêutica",
            "Municípios da base de Assistência Farmacêutica",
            "Conferir a autonomia dos itens com cálculo válido e validar a situação no sistema oficial de estoques.",
            "Evidência: registros que apresentavam autonomia crítica na última carga disponível, sujeitos à validação no sistema oficial.",
            "24–48 h",
        ),
        (
            "Comunicação / Vigilância Ambiental",
            "Estado",
            "Alinhar mensagem de calor e fumaça."
            + (
                " Monitorar o alerta hidrológico local; articular município e Regional; "
                "se o evento de inundação for confirmado, acionar vigilância de DDA, leptospirose e traumas."
                if n_flood
                else ""
            ),
            "Calor, fumaça e sinal hidrológico localizado no recorte disponível.",
            "24–48 h",
        ),
    ]
    cp = [
        (
            "Vigilância Epidemiológica / Laboratório Central de Saúde Pública de Mato Grosso (LACEN-MT)",
            "Regionais prioritárias",
            "Monitorar SRAG e agravos relacionados ao calor.",
            "SRAG e agravos relacionados ao calor no recorte prioritário.",
            "Até a próxima Sala",
        ),
        (
            "Vigilância em Saúde do Trabalhador (VISAT) / Centro de Referência em Saúde do Trabalhador (CEREST) / Gestão de Pessoas",
            "Estado",
            "Orientar proteção de trabalhadores expostos conforme protocolos vigentes.",
            "Exposição ambiental ocupacional.",
            "Até a próxima Sala",
        ),
        (
            "Gestão Regional / Conselho de Secretarias Municipais de Saúde de Mato Grosso (COSEMS-MT)",
            "Municípios estratégicos",
            "Articular planos de ação municipais.",
            "Regionais com maior concentração territorial.",
            "Até a próxima Sala",
        ),
    ]
    pr = [
        (
            "Vigidesastres / Secretaria de Estado de Meio Ambiente de Mato Grosso (SEMA-MT) / Defesa Civil",
            "Estado",
            "Manter leitura conjunta clima–desastre–saúde.",
            "Leitura conjunta clima–desastre–saúde.",
            "Próximas semanas",
        ),
    ]
    return f"""{evid_transversal}

Organizados em três horizontes. Nem todo sinal implica acionamento operacional.

{_quadro_encaminhamento("24 a 48 horas", im)}
{_quadro_encaminhamento("Até a próxima Sala de Situação", cp)}
{_quadro_encaminhamento("Próximas semanas", pr)}
"""


def conclusao_tendencia(snap: dict[str, Any], cenario: dict[str, Any], alertas: dict[str, Any]) -> str:
    if not snap.get("disponivel"):
        return INDISPONIVEL
    n = snap.get("n_municipios")
    crit = snap.get("n_vermelha_roxa")
    delta = snap.get("delta_projecao") or {}
    n_d = snap.get("delta_n_comparavel") or n
    n_melhora = int(delta.get("melhora") or 0)
    n_est = int(delta.get("estabilidade") or 0)
    n_a1 = int(delta.get("aumento_1") or 0)
    n_a2 = int(delta.get("aumento_2plus") or 0)
    n_up = n_a1 + n_a2
    sem = int(snap.get("delta_sem_pareamento") or 0)
    proj = snap.get("niveis_projecao_7d") or {}
    proj_crit = int(proj.get("vermelha") or 0) + int(proj.get("roxa") or 0)

    if not delta:
        tend = "tendência não calculável"
    elif n_up > 0 and n_d and n_up >= max(1, int((n_d or 1) * 0.3)):
        tend = "agravamento disseminado"
    elif n_up > 0:
        tend = "agravamento localizado"
    elif n_est >= max(n_melhora, n_up) and (crit or 0) > (n or 1) * 0.4:
        if n_melhora > 0 and n_up > 0:
            tend = "estabilidade em patamar elevado, com melhora pontual e agravamento localizado"
        elif n_melhora > 0:
            tend = "estabilidade em patamar elevado, com melhora pontual"
        elif n_up > 0:
            tend = "estabilidade em patamar elevado, com agravamento localizado"
        else:
            tend = "estabilidade em patamar elevado"
    elif n_melhora > 0 and n_up == 0:
        tend = "melhora"
    else:
        tend = "persistência"

    n_vig = alertas.get("n_inmet_vigentes")
    regs = snap.get("regionais") or []
    top_reg = ", ".join(str(r.get("regional")) for r in regs[:3]) or "regionais prioritárias"

    if n_up > 0 and n_d:
        if n_melhora == 0:
            melhora_est = "Nenhum município apresenta melhora projetada"
        elif n_melhora == 1:
            melhora_est = "Um município apresenta melhora projetada"
        elif n_melhora == 2:
            melhora_est = "Dois municípios apresentam melhora projetada"
        elif n_melhora == 3:
            melhora_est = "Três municípios apresentam melhora projetada"
        else:
            melhora_est = f"{fmt_int(n_melhora)} municípios apresentam melhora projetada"
        if n_est == 1:
            est_part = "e 1 permanece estável"
        else:
            est_part = f"e {fmt_int(n_est)} permanecem estáveis"
        melhora_txt = f"{melhora_est} {est_part}."
        pred_bloco = (
            f"Para os próximos sete dias, a projeção indica **{tend}**: "
            f"**{fmt_frac(n_up, n_d)}** municípios comparáveis apresentam elevação da classificação, "
            f"sendo {fmt_int(n_a1)} com aumento de um nível e {fmt_int(n_a2)} com aumento de dois ou mais níveis. "
            f"{melhora_txt} "
            f"Ao final do horizonte projetado, **{fmt_frac(proj_crit, n)}** estarão nas classes vermelha ou roxa, "
            "caso o cenário estimado se confirme."
        )
        mqa = snap.get("model_qa") or {}
        if mqa.get("MODEL_SATURATION_WARNING"):
            pred_bloco += (
                " A projeção apresenta elevada concentração nas classes "
                "superiores e deve ser reavaliada nas rodadas "
                "subsequentes, especialmente diante da ampla influência "
                "dos componentes de persistência térmica e onda de calor."
            )
    else:
        pred_bloco = (
            f"Para os próximos sete dias, entre **{fmt_int(n_d)}** municípios com dados comparáveis, "
            f"predomina estabilidade ({fmt_frac(n_est, n_d)}), com melhora em {fmt_frac(n_melhora, n_d)}."
        )
        if n_melhora == 0:
            pred_bloco = pred_bloco.replace(
                f"com melhora em {fmt_frac(n_melhora, n_d)}.",
                "Não há municípios com melhora projetada nesta rodada.",
            )

    n_vig = alertas.get("n_inmet_vigentes")
    vig_sint = str(alertas.get("inmet_vigentes_sintese_md") or "").lower()
    aviso_umi_inmet = bool(
        n_vig
        and any(k in vig_sint for k in ("umidade", "seca", "tempo seco", "baixa umidade"))
    )
    padrao_obs = (
        "O padrão territorial da rodada é marcado por calor e exposição à fumaça/material particulado"
    )
    if aviso_umi_inmet:
        padrao_obs += ", em contexto de avisos meteorológicos de baixa umidade emitidos pelo INMET."
    else:
        padrao_obs += ", associado a sinais localizados de baixa disponibilidade hídrica."

    return f"""A Semana Epidemiológica mantém cenário de **elevada atenção** em Mato Grosso, com **{fmt_frac(crit, n)}** municípios nas classes vermelha ou roxa no momento da emissão. {padrao_obs}

As maiores concentrações de risco encontram-se em **{top_reg}**, entre outras regionais. A sobreposição com aldeias indígenas e municípios com comunidades quilombolas certificadas reforça a necessidade de abordagem territorial e articulação específica.

Para a saúde, a prioridade é a vigilância de agravos respiratórios e relacionados ao calor, a organização da atenção nos municípios prioritários e a conferência de insumos estratégicos pela Assistência Farmacêutica no sistema oficial de estoques.

{pred_bloco}
{f" Sem pareamento válido: {fmt_pareamento(sem, n)}" if sem else ""}

A magnitude da mudança projetada exige acompanhamento das próximas rodadas e interpretação dos determinantes do modelo, especialmente porque a situação observada no momento da emissão apresenta **{fmt_frac(crit, n)}** nas classes vermelha ou roxa. Alertas oficiais vigentes do Instituto Nacional de Meteorologia (INMET) nesta emissão: {fmt_int(n_vig) if n_vig is not None else INDISPONIVEL}.

**Tendência: {tend}.**

Entre as principais limitações desta rodada estão a cobertura parcial dos indicadores hidrológicos, a diferença de competência temporal entre bases epidemiológicas e a indisponibilidade de alguns indicadores municipais.

Encaminhamento prioritário: validar a lista territorial e os determinantes da projeção na Sala de Situação e articular Regionais, Assistência Farmacêutica e Vigilância Ambiental nas próximas 24–48 horas.
"""