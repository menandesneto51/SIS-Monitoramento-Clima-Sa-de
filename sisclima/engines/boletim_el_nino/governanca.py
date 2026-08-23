# -*- coding: utf-8 -*-
"""Governança SES-MT, Saúde do Trabalhador, encaminhamentos e conclusão."""
from __future__ import annotations

from typing import Any

from sisclima.engines.boletim_el_nino.constants import INDISPONIVEL
from sisclima.engines.boletim_el_nino.formatters import fmt_frac, fmt_int, fmt_num, md_table
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
            "UNIEVS/CIEVS-MT",
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
            "Autonomia de insumos críticos na base SAF",
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
            "Cenário de calor, baixa umidade e fumaça",
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
    dc_txt = (
        f" Atual: {fmt_frac(crit, n)}; projeção ~7 dias: {fmt_frac(proj_crit, n)}; "
        f"agravamento: {fmt_frac(n_up, n_d)} comparáveis"
        if crit is not None and n and proj_crit
        else ""
    )
    linhas = [
        "- **SEMA-MT** — compartilhar o cenário de qualidade do ar, focos de calor e territórios prioritários para avaliação ambiental integrada"
        + (f" (PM2,5 elevado em {fmt_int(n25)} municípios)" if n25 else "")
        + ".",
        "- **Defesa Civil Estadual** — compartilhar municípios classificados em níveis elevados e a projeção para os próximos sete dias"
        + (dc_txt if dc_txt else (f" ({fmt_int(crit)} em classes vermelha ou roxa)" if crit is not None else ""))
        + ".",
        "- **Corpo de Bombeiros Militar** — articular informações sobre incêndios florestais nos territórios prioritários"
        + (f" (acumulado de {fmt_int(focos)} focos em sete dias)" if focos else "")
        + ".",
        "- **COSEMS-MT / municípios** — pactuar acompanhamento dos planos de ação nos municípios estratégicos.",
        "- **DSEI / SESAI e FUNAI** — articular continuidade do cuidado em territórios indígenas com risco climático elevado.",
        "- **INMET / CEMADEN / INPE / ANA / SGB** — utilizar apenas produtos oficiais já consultados nesta rodada.",
    ]
    return "\n".join(linhas)


def saude_trabalhador(snap: dict[str, Any]) -> str:
    return """O Ministério da Saúde reconhece trabalhadores externos urbanos e rurais como particularmente expostos a ondas de calor e eventos climáticos extremos.

> **Limitação:** o boletim ainda não dispõe de estimativa do número de trabalhadores potencialmente expostos.

**Exposições ocupacionais coerentes com o cenário da semana:** calor extremo, radiação solar, baixa umidade, fumaça, PM2,5, incêndios e esforço físico ao ar livre.

**Grupos ocupacionais a considerar:** trabalhadores rurais e da construção; serviços urbanos externos; coleta de resíduos e saneamento; transporte e entregadores; agentes comunitários e de endemias; brigadistas, bombeiros e Defesa Civil; equipes de unidades de saúde e ambientais.

**Ações:** CEREST/VISAT — monitorar agravos e orientar setores; Gestão de Pessoas — revisar proteção dos trabalhadores da própria SES-MT; municípios — orientar ações de vigilância e proteção aos grupos ocupacionais potencialmente expostos, conforme protocolos vigentes.
"""


def populacoes_prioritarias(snap: dict[str, Any]) -> str:
    n = snap.get("n_municipios")
    n25 = snap.get("n_pm25_25")
    rows = [
        ["Crianças e idosos", "Calor e fumaça", f"PM2,5 ≥ 25 µg/m³: {fmt_frac(n25, n)}" if n else INDISPONIVEL, "Atenção básica e comunicação de risco"],
        ["Gestantes e puérperas", "Calor / desidratação", "Critério de calor seco municipal quando Tmáx ≥ 37 °C e UR ≤ 30%", "Continuidade do cuidado"],
        ["Pessoas com doenças crônicas", "Calor e qualidade do ar", "Sobreposição com classes vermelha e roxa", "APS e regulação"],
        ["Pessoas com deficiência", "Calor e qualidade do ar", "Sobreposição com classes vermelha e roxa", "APS, assistência social e redes de cuidado"],
        ["Trabalhadores expostos", "Calor, sol, fumaça", "Cenário estadual de exposição externa", "VISAT/CEREST e gestão de pessoas"],
        ["Povos indígenas", "Território e clima", "Aldeias cruzadas com classificação de risco ARARAS", "DSEI/SESAI e SMS"],
        ["Comunidades quilombolas", "Território e clima", "Comunidades certificadas (Palmares); certificação ≠ titulação", "SMS e organizações locais"],
        ["Populações do campo, floresta e águas", "Estiagem, fogo, água", "Portaria n.º 0590/2026/GBSES", "Articulação intersetorial"],
        ["População em situação de rua", "Calor e fumaça", "Sem quantitativo nesta rodada", "Rede municipal e socioassistencial"],
        ["Pessoas privadas de liberdade", "Calor e fumaça", "Sem quantitativo nesta rodada", "Sistema prisional e atenção à saúde"],
    ]
    return md_table(["População/território", "Exposição predominante", "Evidência territorial", "Ação prioritária"], rows)


def sintese_territorial(snap: dict[str, Any]) -> str:
    if not snap.get("disponivel"):
        return INDISPONIVEL
    regs = snap.get("regionais") or []
    top_reg = ", ".join(str(r.get("regional")) for r in regs[:5]) or INDISPONIVEL
    ext = snap.get("extremos") or {}
    delta = snap.get("delta_projecao") or {}
    n_d = snap.get("delta_n_comparavel") or snap.get("n_municipios")
    return f"""- Regionais com maior concentração nas classes vermelha e roxa: **{top_reg}**.
- Maior Tmáx municipal: **{(ext.get('tmax') or {}).get('municipio') or '—'}** ({fmt_num((ext.get('tmax') or {}).get('tmax'), 1, ' °C')}).
- Maior PM2,5 municipal: **{(ext.get('pm25') or {}).get('municipio') or '—'}**.
- Maior acumulado de focos (7 dias): **{(ext.get('focos') or {}).get('municipio') or '—'}**.
- Persistência: estabilidade de classe em {fmt_frac(delta.get('estabilidade'), n_d) if delta else INDISPONIVEL}.
- Melhora projetada: {fmt_frac(delta.get('melhora'), n_d) if delta else INDISPONIVEL}.
- Limitação dos dados. Cobertura hidrológica: {fmt_frac(snap.get('cobertura_hidro'), snap.get('n_municipios'))}.
  Cobertura de focos: {"não caracterizada por esta estrutura da base" if (snap.get("cobertura_focos") is not None and snap.get("n_com_focos_7d") is not None and int(snap.get("cobertura_focos")) == int(snap.get("n_com_focos_7d"))) else fmt_frac(snap.get("cobertura_focos"), snap.get("n_municipios"))}.
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
    evid_proj = (
        f"Atual: {fmt_frac(crit, n)} vermelho/roxo; projeção ~7 dias: {fmt_frac(proj_crit, n)}; "
        f"agravamento: {fmt_frac(n_up, n_d)} comparáveis."
        if crit is not None and n and proj_crit
        else "Classificação elevada e projeção operacional."
    )
    im = [
        (
            "UNIEVS/CIEVS-MT",
            "Estado / municípios prioritários",
            "Validar a priorização territorial e consolidar o cenário para a Sala de Situação.",
            evid_proj,
            "24–48 h",
        ),
        (
            "Atenção à Saúde",
            "Municípios prioritários",
            "Avaliar capacidade assistencial e necessidade de contingenciamento conforme evolução da demanda.",
            evid_proj,
            "24–48 h",
        ),
        (
            "Assistência Farmacêutica (SAF)",
            "Municípios da base SAF",
            "Conferir a autonomia dos itens com cálculo válido e validar a situação no sistema oficial de estoques.",
            "Combinações com estoque crítico calculável (observar defasagem da carga).",
            "24–48 h",
        ),
        (
            "Comunicação / Vigilância Ambiental",
            "Estado",
            "Alinhar mensagem de calor e fumaça.",
            evid_proj,
            "24–48 h",
        ),
    ]
    cp = [
        (
            "Vigilância Epidemiológica / Laboratório Central de Saúde Pública de Mato Grosso (LACEN-MT)",
            "Regionais prioritárias",
            "Monitorar SRAG e agravos relacionados ao calor.",
            evid_proj,
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
            evid_proj,
            "Até a próxima Sala",
        ),
    ]
    pr = [
        (
            "Vigidesastres / SEMA / Defesa Civil",
            "Estado",
            "Manter leitura conjunta clima–desastre–saúde.",
            evid_proj,
            "Próximas semanas",
        ),
    ]
    return f"""## Encaminhamentos recomendados

Organizados em três horizontes. Nem todo sinal implica acionamento operacional.

{_quadro_encaminhamento("Imediatos — 24 a 48 horas", im)}
{_quadro_encaminhamento("Curto prazo — até a próxima Sala de Situação", cp)}
{_quadro_encaminhamento("Preparação — próximas semanas", pr)}
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
        pred_bloco = (
            f"Para os próximos sete dias, a projeção indica **{tend}**: "
            f"**{fmt_frac(n_up, n_d)}** municípios comparáveis apresentam elevação da classificação, "
            f"sendo {fmt_int(n_a1)} com aumento de um nível e {fmt_int(n_a2)} com aumento de dois ou mais níveis. "
            f"{'Apenas um município apresenta melhora' if n_melhora == 1 else f'{fmt_int(n_melhora)} municípios apresentam melhora'}"
            f" e {fmt_int(n_est)} permanecem estáveis. "
            f"Ao final do horizonte projetado, **{fmt_frac(proj_crit, n)}** estarão nas classes vermelha ou roxa, "
            "caso o cenário estimado se confirme."
        )
    else:
        pred_bloco = (
            f"Para os próximos sete dias, entre **{fmt_int(n_d)}** municípios com dados comparáveis, "
            f"predomina estabilidade ({fmt_frac(n_est, n_d)}), com melhora em {fmt_frac(n_melhora, n_d)}."
        )

    return f"""## Conclusão e tendência para a próxima semana

A Semana Epidemiológica mantém cenário de **elevada atenção** em Mato Grosso, com **{fmt_frac(crit, n)}** municípios nas classes vermelha ou roxa no momento da emissão. O padrão territorial é marcado principalmente pela combinação de calor, baixa umidade e exposição à fumaça.

As maiores concentrações de risco encontram-se em **{top_reg}**, entre outras regionais. A sobreposição com aldeias indígenas e municípios com comunidades quilombolas certificadas reforça a necessidade de abordagem territorial e articulação específica.

Para a saúde, a prioridade é a vigilância de agravos respiratórios e relacionados ao calor, a organização da atenção nos municípios prioritários e a conferência de insumos estratégicos pela Assistência Farmacêutica no sistema oficial de estoques.

{pred_bloco}
{f" Um município sem pareamento válido entre situação atual e projeção nesta rodada." if sem == 1 else (f" {fmt_int(sem)} municípios sem pareamento válido nesta rodada." if sem else "")}

A magnitude da mudança projetada exige acompanhamento das próximas rodadas e interpretação dos determinantes do modelo, especialmente porque a situação observada no momento da emissão apresenta **{fmt_frac(crit, n)}** nas classes vermelha ou roxa. Alertas oficiais vigentes do Instituto Nacional de Meteorologia (INMET) nesta emissão: {fmt_int(n_vig) if n_vig is not None else INDISPONIVEL}.

**Tendência: {tend}.**

Entre as principais limitações desta rodada estão a cobertura parcial dos indicadores hidrológicos, a diferença de competência temporal entre bases epidemiológicas e a indisponibilidade de alguns indicadores municipais.

Encaminhamento prioritário: validar a lista territorial e os determinantes da projeção na Sala de Situação e articular Regionais, Assistência Farmacêutica e Vigilância Ambiental nas próximas 24–48 horas.
"""