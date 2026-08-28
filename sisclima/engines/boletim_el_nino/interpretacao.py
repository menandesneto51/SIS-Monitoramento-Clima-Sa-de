# -*- coding: utf-8 -*-
"""Interpretações determinísticas a partir de valores já calculados."""
from __future__ import annotations

from typing import Any

from sisclima.engines.boletim_el_nino.constants import (
    FOGO_SATELITE_REFERENCIA_CURTO,
    FOGO_SATELITE_REFERENCIA_PUBLICO,
    INDISPONIVEL,
    NAO_CALCULADO,
)
from sisclima.engines.boletim_el_nino.formatters import fmt_frac, fmt_int, fmt_num, fmt_pareamento, fmt_plural


def _n(snap: dict[str, Any]) -> int | None:
    n = snap.get("n_municipios")
    return int(n) if n else None


def interpretar_temperatura(snap: dict[str, Any]) -> str:
    n = _n(snap)
    tmax = snap.get("tmax_mediana")
    if tmax is None or n is None:
        return INDISPONIVEL
    ext = (snap.get("extremos") or {}).get("tmax") or {}
    mun_ext = ext.get("municipio") or "município não identificado"
    val_ext = ext.get("tmax")
    cob = snap.get("cobertura_tmax") or n
    linhas = [
        f"Temperatura máxima mediana: **{fmt_num(tmax, 1, ' °C')}** "
        f"(mín. {fmt_num(snap.get('tmax_min'), 1, ' °C')}; máx. {fmt_num(snap.get('tmax_max'), 1, ' °C')}).",
        f"Cobertura: {fmt_frac(cob, n)} municípios com dado válido.",
        f"Municípios com Tmáx ≥ 37 °C: {fmt_frac(snap.get('n_tmax_37'), n)}.",
    ]
    if val_ext is not None:
        linhas.append(f"Extremo municipal: **{fmt_num(val_ext, 1, ' °C')}** em {mun_ext}.")
    if snap.get("tmax_p90") is not None:
        linhas.append(
            f"Percentil 90 da rodada: {fmt_num(snap['tmax_p90'], 1, ' °C')} "
            "(distribuição desta rodada, não climatologia histórica)."
        )
    linhas.append(
        "A mediana estadual não descreve o recorte mais exposto. "
        "Tmáx ≥ 37 °C e UTCI ≥ 32 °C descrevem exposição térmica nesta rodada; "
        "a combinação Tmáx ≥ 37 °C com UR ≤ 30% define calor seco, distinto de onda de calor. "
        "Limitação: a rodada não dispõe de climatologia municipal validada para comparação histórica deste indicador."
    )
    return " ".join(linhas)


def interpretar_umidade(snap: dict[str, Any]) -> str:
    n = _n(snap)
    ur = snap.get("umidade_mediana")
    if ur is None or n is None:
        return INDISPONIVEL
    n30 = snap.get("n_umidade_30")
    cob = snap.get("cobertura_umidade") or n
    return (
        f"Umidade relativa mediana estadual: **{fmt_num(ur, 0, '%')}** "
        f"(mín. {fmt_num(snap.get('umidade_min'), 0, '%')}; máx. {fmt_num(snap.get('umidade_max'), 0, '%')}). "
        f"Municípios com UR ≤ 30% (extremo de atenção): {fmt_frac(n30, n)}. "
        f"Cobertura: {fmt_frac(cob, n)}. "
        "O limiar de 30% é parâmetro operacional do ARARAS para desconforto, ressecamento de vias aéreas e risco de fogo; "
        "não substitui o aviso oficial do Instituto Nacional de Meteorologia (INMET)."
    )


def interpretar_pm25(snap: dict[str, Any]) -> str:
    n = _n(snap)
    med = snap.get("pm25_mediana")
    if med is None or n is None:
        return INDISPONIVEL
    n25 = snap.get("n_pm25_25")
    cob = snap.get("cobertura_pm25") or n
    p90 = snap.get("pm25_p90")
    extra = f" P90 da rodada: {fmt_num(p90, 1, ' µg/m³')}." if p90 is not None else ""
    return (
        f"PM2,5 mediano: **{fmt_num(med, 1, ' µg/m³')}** "
        f"(mín. {fmt_num(snap.get('pm25_min'), 1)}; máx. {fmt_num(snap.get('pm25_max'), 1, ' µg/m³')}).{extra} "
        f"{fmt_frac(n25, n)} apresentaram PM2,5 igual ou superior a 25 µg/m³ "
        "(parâmetro operacional de atenção sanitária do painel, alinhado a faixas de qualidade do ar). "
        f"Cobertura espacial: {fmt_frac(cob, n)}. "
        "Interpretação sanitária: exposição à fumaça/partículas finas, com atenção a agravos respiratórios — "
        "associação temporal, sem inferência causal."
    )


def interpretar_fogo(snap: dict[str, Any]) -> str:
    n = _n(snap)
    focos = snap.get("focos_7d_total")
    if focos is None or n is None:
        return INDISPONIVEL
    n_com = snap.get("n_com_focos_7d")
    cob = snap.get("cobertura_focos")
    ext = (snap.get("extremos") or {}).get("focos") or {}
    mun = ext.get("municipio")
    val = ext.get("focos_queimadas_7d")
    ff = snap.get("fire_facts") or {}
    cob = ff.get("coverage") if ff.get("coverage") is not None else cob
    n_com = ff.get("detected") if ff.get("detected") is not None else n_com
    total = ff.get("total")
    if total is not None:
        focos = total
    deteccoes = snap.get("deteccoes_7d_total")
    if deteccoes is None:
        deteccoes = ff.get("deteccoes_total")
    partes: list[str] = []
    ref = FOGO_SATELITE_REFERENCIA_PUBLICO
    if n_com is not None and n is not None and focos is not None:
        pct = fmt_num(100.0 * float(n_com) / float(n), 1, "%")
        partes.append(
            f"Foram registrados {fmt_int(focos)} focos de calor pelo {ref}, "
            f"utilizado para comparação temporal da série histórica, em {fmt_int(n_com)} de {fmt_int(n)} "
            f"municípios ({pct}) no acumulado de sete dias."
        )
    elif n_com is not None and n is not None:
        partes.append(
            f"Foram detectados focos de calor ({FOGO_SATELITE_REFERENCIA_CURTO}) em {fmt_int(n_com)} de {fmt_int(n)} municípios "
            f"({fmt_num(100.0 * float(n_com) / float(n), 1, '%')}) no acumulado de sete dias."
        )
    elif focos is not None:
        partes.append(
            f"**{fmt_int(focos)} focos de calor** detectados pelo {ref} "
            f"no acumulado de sete dias (fonte INPE/BDQueimadas integrada ao ARARAS)."
        )
    if deteccoes is not None and focos is not None and float(deteccoes) > float(focos):
        partes.append(
            f"O conjunto multi-satélite registrou {fmt_int(deteccoes)} detecções no período; "
            f"essas detecções não equivalem a {fmt_int(deteccoes)} incêndios ou focos distintos."
        )
    if mun and val is not None:
        partes.append(f"{mun} concentrou o maior número, com {fmt_int(val)} focos no satélite de referência.")
    return " ".join(partes) if partes else INDISPONIVEL


def interpretar_hidrologia(snap: dict[str, Any]) -> str:
    n = _n(snap)
    cob = snap.get("cobertura_hidro")
    if n is None:
        return INDISPONIVEL
    if cob is None:
        return "Dados hidrológicos municipais indisponíveis nesta rodada."
    if cob < n:
        lim = (
            f"**Limitação dos dados.** A cobertura hidrológica desta rodada corresponde a "
            f"{fmt_frac(cob, n)}; os resultados não devem ser extrapolados para todo o estado."
        )
    else:
        lim = f"Cobertura hidrológica: {fmt_frac(cob, n)}."
    solo = snap.get("solo_mediana")
    solo_txt = ""
    if solo is not None:
        solo_txt = (
            f" Índice de saturação do solo: mediana **{fmt_num(solo, 0)}/100** "
            f"(escala normalizada 0–100 a partir de umidade volumétrica Open-Meteo; "
            f"parâmetro entre ponto de murcha 0,05 e saturação de referência 0,42 m³/m³). "
            f"**{fmt_num(solo, 0)} pontos** em escala de 0 a 100; "
            "sem faixa de interpretação institucional validada nesta rodada."
        )
    hf = snap.get("hydro_facts") or {}
    recorte = ""
    if hf.get("coverage"):
        low = int(hf.get("low_availability") or 0)
        flood = int(hf.get("flood_risk_high") or 0)
        hab = int(hf.get("habitual") or 0)
        recorte = (
            f" No recorte hidrológico disponível, {fmt_plural(low, 'município', 'municípios')} "
            f"{'apresenta' if low == 1 else 'apresentam'} sinal de baixa disponibilidade hídrica, "
            f"{fmt_int(flood)} {'apresenta' if flood == 1 else 'apresentam'} risco elevado de inundação "
            f"e {fmt_int(hab)} {'está' if hab == 1 else 'estão'} em situação hidrológica habitual."
        )
    return (
        f"{lim}{recorte} "
        "Os sinais de baixa disponibilidade hídrica local **não equivalem** automaticamente "
        "à classificação do Monitor de Secas (produto distinto, com outra escala e competência temporal)."
        f"{solo_txt}"
    )


def interpretar_tendencia(snap: dict[str, Any]) -> str:
    from sisclima.engines.boletim_el_nino.formatters import fmt_plural

    d = snap.get("delta_projecao") or {}
    n = snap.get("delta_n_comparavel") or _n(snap)
    if not d or n is None:
        return NAO_CALCULADO
    sem = snap.get("delta_sem_pareamento") or 0
    txt = (
        f"Na projeção de aproximadamente sete dias, entre **{fmt_int(n)}** municípios com dados comparáveis: "
        f"melhora em {fmt_frac(d.get('melhora', 0), n)}; "
        f"estabilidade em {fmt_frac(d.get('estabilidade', 0), n)}; "
        f"aumento de 1 nível em {fmt_frac(d.get('aumento_1', 0), n)}; "
        f"aumento de 2 ou mais níveis em {fmt_frac(d.get('aumento_2plus', 0), n)}."
    )
    if sem:
        tot = _n(snap)
        par = fmt_pareamento(sem, tot)
        txt += f" Sem pareamento válido: {par}" if par else f" Sem pareamento válido: {fmt_plural(sem, 'município', 'municípios')}."
    return txt


def analisar_cenario_bloco(titulo: str, paragrafos: list[str]) -> str:
    corpo = "\n\n".join(p for p in paragrafos if p)
    return f"**{titulo}**\n\n{corpo}"


def leitura_integrada(snap: dict[str, Any]) -> str:
    if not snap.get("disponivel"):
        return INDISPONIVEL
    n = _n(snap) or 0
    crit = snap.get("n_vermelha_roxa") or 0
    n37 = snap.get("n_tmax_37") or 0
    n_utci = snap.get("n_utci_32") or 0
    n25 = snap.get("n_pm25_25") or 0
    focos = snap.get("focos_7d_total")
    tmax = snap.get("tmax_mediana")
    calor = (n37 and n > 0) or (tmax is not None and tmax >= 35)
    fumaca = n > 0 and n25 >= max(1, int(0.10 * n))
    fogo_alto = focos is not None and focos >= 1000
    if calor and fumaca:
        return (
            f"Os indicadores desta semana mostram convergência de calor "
            f"({fmt_frac(n37, n)} com Tmáx ≥ 37 °C; {fmt_frac(n_utci, n)} com UTCI ≥ 32 °C) "
            f"e exposição à fumaça ({fmt_frac(n25, n)} com PM2,5 ≥ 25 µg/m³)"
            + (f", com {fmt_int(focos)} focos no satélite de referência em sete dias" if fogo_alto else "")
            + f". **{fmt_frac(crit, n)}** permaneceram nas classes vermelha ou roxa. "
            "A sobreposição desses fatores aumenta a necessidade de vigilância de agravos respiratórios e relacionados ao calor, "
            "especialmente nos municípios que permanecem em classes elevadas na projeção de sete dias."
        )
    return (
        f"Nesta rodada, **{fmt_frac(crit, n)}** municípios estão nas classes vermelha ou roxa. "
        "A leitura integrada deve considerar, em conjunto, temperatura, umidade, qualidade do ar e hidrologia, "
        "sem tratar correlação espacial como causalidade."
    )


def interpretar_medidor(med: dict[str, Any] | None, snap: dict[str, Any]) -> str:
    if not med or not med.get("disponivel"):
        return NAO_CALCULADO
    n = _n(snap)
    score = med.get("score")
    alvo = med.get("alvo_critico_municipios")
    atual = med.get("criticos_atuais")
    eta = med.get("eta_critico_dias")
    eta_ok = bool(med.get("eta_robusto"))
    acima = bool(med.get("acima_referencial")) or (
        atual is not None and alvo is not None and int(atual) >= int(alvo)
    )
    proj = snap.get("niveis_projecao_7d") or {}
    proj_crit = int(proj.get("vermelha") or 0) + int(proj.get("roxa") or 0)
    if n and atual is not None and alvo:
        dist = int(atual) - int(alvo)
        pct_atual = 100.0 * atual / n
        pct_ref = 70.0
        diff_pp = pct_atual - pct_ref
        partes = [
            f"Score de trajetória: **{fmt_num(score, 1)}/100** (faixa: {med.get('classe')}).",
            "Escala: 0 = nenhum município nas classes vermelha e roxa e sem reforço de tendência/PM2,5/UR; "
            "100 = saturação dos componentes (proporção crítica, municípios em agravamento, PM2,5 e UR).",
            f"Referencial crítico: {fmt_int(alvo)} municípios (70,0% do estado).",
            f"Situação atual: {fmt_int(atual)} municípios ({fmt_num(pct_atual, 1, '%')} do estado).",
        ]
        if acima:
            partes.insert(0, "**Situação acima do referencial crítico.**")
            partes.append(
                f"Diferença em relação ao referencial: **{fmt_int(abs(dist))}** municípios "
                f"({fmt_num(abs(diff_pp), 1)} pontos percentuais) acima."
            )
        else:
            partes.append(
                f"Diferença em relação ao referencial: **{fmt_int(abs(dist))}** municípios "
                f"({fmt_num(abs(diff_pp), 1)} pontos percentuais) abaixo."
            )
            if eta is not None and eta_ok:
                n_rod = med.get("n_rodadas_temporais") or "N"
                partes.append(
                    f"Tempo estimado até o referencial: **~{fmt_num(eta, 0)} dias**, "
                    f"se mantida a trajetória observada nas últimas {n_rod} rodadas."
                )
            else:
                partes.append(
                    "Tempo até o referencial: **não estimável com robustez nesta rodada** "
                    "(exige pelo menos três rodadas temporais válidas, tendência positiva consistente "
                    "e denominadores comparáveis)."
                )
        if proj_crit:
            partes.append(
                f"**Leitura conjunta:** a projeção de sete dias reforça a necessidade de acompanhamento antecipado "
                f"(estima **{fmt_frac(proj_crit, n)}** municípios nas classes vermelha ou roxa), "
                "embora o medidor de trajetória e a projeção utilizem metodologias e horizontes distintos."
            )
        return " ".join(partes)
    return NAO_CALCULADO
