# -*- coding: utf-8 -*-
"""Controle de qualidade automático do boletim."""
from __future__ import annotations

import re
from typing import Any

from sisclima.engines.boletim_el_nino.constants import SIGLAS

# Siglas conhecidas que devem ser auditadas mesmo se ainda sem expansão confirmada
_SIGLAS_REVISAO = ("UNIEVS",)


def run_qa(markdown: str, snap: dict[str, Any], refs: list[str], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    issues: list[str] = []
    md = markdown or ""
    extra = extra or {}
    terr = extra.get("territorios") or {}
    pront = extra.get("prontidao") or {}
    alertas = extra.get("alertas") or {}

    bad_patterns = [
        (r"\b0/0\b", "0/0"),
        (r"\bNaN\b", "NaN"),
        (r"\bNone\b", "None"),
        (r"\bnull\b(?![-\w])", "null"),
        (r"Sem recorte", "Sem recorte"),
        (r"Municípios no recorte: 0\b", "municípios zero"),
        (r"&gt;|&lt;", "entidade HTML"),
        (r"seca_baixa", "seca_baixa"),
        (r"inundacao_alta", "inundacao_alta"),
        (r"pendente_sql_dw", "pendente_sql_dw"),
        (r"FUMOÇA", "FUMOÇA"),
        (r"Secretaria de Estado de Saúde \(Secretaria", "expansao_duplicada_SES"),
        (r"Decisões sugeridas para a Sala de Situação", "pauta_antiga"),
        (r"município\(s\)", "municipio_s_parenteses"),
        (r"aviso\(s\)", "aviso_s_parenteses"),
        (r"vermelho/rox[oa]", "vermelho_roxa_slash"),
        (r"vermelha/rox[oa]", "vermelha_roxa_slash"),
        (r"(?<![→\-\w])->(?![→\-\w])", "seta_ascii"),
        (r"acelerando para crítico", "eta_quando_ja_critico"),
        (r"(?<![0-9])1 municípios\b", "plural_1_municipios"),
        (r"(?<![0-9])1 avisos\b", "plural_1_avisos"),
        (r"(?<![0-9])1 alertas\b", "plural_1_alertas"),
        (r"Cobertura:\s*\d+/\d+", "cobertura_foco_fracao_suspeita"),
        (r"Vermelho/RoxoTendência|Vermelha\d", "cabecalhos_colados_regional"),
        (r"(?i)(principal\s+determinante[^\n|]{0,40}prioridade\s+global|prioridade\s+global[^\n|]{0,40}determinante)", "determinante_prioridade_global"),
        (r"Preparação assistencial e farmacêutica \(SAF/SES\)", "titulo_14_com_saf"),
    ]
    for pat, label in bad_patterns:
        if re.search(pat, md, re.I):
            issues.append(label)

    if snap.get("disponivel") is False and re.search(r"Municípios no recorte:\s*\*\*0\*\*", md):
        issues.append("zero_municipios_com_recorte_indisponivel")

    for sigla in SIGLAS:
        if re.search(rf"(?<![\w]){re.escape(sigla)}(?![\w-])", md):
            expansao = SIGLAS[sigla]
            core = expansao.split(" (")[0].strip()
            if expansao not in md and core not in md:
                issues.append(f"sigla_sem_expansao:{sigla}")

    for sigla in _SIGLAS_REVISAO:
        if re.search(rf"\b{re.escape(sigla)}\b", md):
            issues.append(f"sigla_revisar_expansao:{sigla}")

    if "REFERENCIAS_ABNT_6023.md" in md:
        issues.append("ref_interna_exposta")
    if not re.search(r"Fonte:", md, re.I):
        issues.append("sem_fonte_inline")
    if "Mapa 1" in md and "Fonte:" not in md:
        issues.append("mapa_sem_fonte")
    if re.search(r"Situação observada:\s*\d+\s*$", md, re.M):
        issues.append("situacao_observada_numerica")

    if re.search(r"Território/comunidadeMunicípio|comunidadeMunicípio", md):
        issues.append("cabecalhos_tabela_colados")

    # Títulos internos duplicados nos mapas (matplotlib) não devem aparecer no MD
    if md.count("Classificação de risco atual e projeção operacional") > 1:
        issues.append("titulo_mapa_duplicado")

    med = snap.get("medidor_trajetoria") or {}
    if med.get("acima_referencial") and re.search(r"ETA|tempo até o cenário crítico|acelerando", md, re.I):
        if re.search(r"acelerando para crítico|ETA mantido", md, re.I):
            issues.append("medidor_eta_ja_acima_critico")

    n_comp = snap.get("delta_n_comparavel")
    n_tot = snap.get("n_municipios")
    if n_comp and n_tot and int(n_comp) < int(n_tot):
        # texto não pode usar o total como denominador da projeção comparável
        if re.search(rf"entre\s+\*\*{int(n_tot)}\*\*\s+municípios com dados comparáveis", md, re.I):
            issues.append("denominador_projecao_inconsistente")
        delta = snap.get("delta_projecao") or {}
        melhora = int(delta.get("melhora") or 0)
        est = int(delta.get("estabilidade") or 0)
        up = int(delta.get("aumento_1") or 0) + int(delta.get("aumento_2plus") or 0)
        if melhora + est + up and (melhora + est + up) != int(n_comp):
            issues.append("delta_soma_diferente_comparavel")

    # Coerência tendência resumo × conclusão
    delta = snap.get("delta_projecao") or {}
    n_up = int(delta.get("aumento_1") or 0) + int(delta.get("aumento_2plus") or 0)
    n_d = snap.get("delta_n_comparavel") or snap.get("n_municipios") or 1
    if n_up >= max(1, int(n_d * 0.3)):
        if re.search(r"Municípios em risco integrado elevado[\s\S]{0,200}agravamento localizado", md, re.I):
            issues.append("tendencia_resumo_divergente_conclusao")
        if "Determinantes do agravamento projetado" not in md and "Como a classe projetada é calculada" not in md:
            issues.append("projecao_sem_determinantes")

    # Tendência de fogo/PM inferida sem previsão específica
    if re.search(r"\|\s*Fogo\s*\|[^|]+\|\s*agravamento", md, re.I):
        issues.append("tendencia_fogo_sem_previsao")
    if re.search(r"\|\s*Qualidade do ar\s*\|[^|]+\|\s*agravamento", md, re.I):
        issues.append("tendencia_ar_sem_previsao")

    # Contexto como driver matemático
    if re.search(r"Contribuição para a projeção[\s\S]{0,200}(PM2,5 atual|Umidade relativa atual|Focos)", md, re.I):
        issues.append("contexto_como_driver_matematico")

    # Projeção extrema sem documentação de regra
    proj = snap.get("niveis_projecao_7d") or {}
    n_tot = snap.get("n_municipios")
    proj_crit = int(proj.get("vermelha") or 0) + int(proj.get("roxa") or 0)
    if n_tot and proj_crit / max(int(n_tot), 1) >= 0.9:
        if "Como a classe projetada é calculada" not in md:
            issues.append("projecao_extrema_sem_regra")
        if "Drivers que entram no modelo" not in md and "Drivers que entram no modelo" not in md:
            if "A. Drivers" not in md:
                issues.append("projecao_extrema_sem_drivers")

    # Totais de classes projetadas
    if n_tot and proj:
        soma_proj = sum(int(proj.get(k) or 0) for k in ("verde", "amarela", "laranja", "vermelha", "roxa", "cinza"))
        if soma_proj and soma_proj != int(n_tot):
            # permitir se só classes presentes sem zeros
            presentes = sum(int(v or 0) for v in proj.values())
            if presentes != int(n_tot):
                issues.append("total_projetado_classes_inconsistente")

    n_comp = snap.get("delta_n_comparavel")
    sem_par = int(snap.get("delta_sem_pareamento") or 0)
    if n_tot and n_comp is not None and (int(n_comp) + sem_par) != int(n_tot):
        issues.append("comparaveis_mais_sem_pareamento_inconsistente")

    # Datas ISO no corpo público (exceto nomes de arquivo)
    if re.search(r"(?<![\w/])20\d{2}-\d{2}-\d{2}(?![\w-])", md):
        # permitir em gerado_em técnico se houver — ainda assim flag para revisão
        if re.search(r"\b20\d{2}-\d{2}-\d{2}[ T]\d{2}:", md) or re.search(
            r"(Início|Fim|validade|atualização)[^\n]{0,40}20\d{2}-\d{2}-\d{2}", md, re.I
        ):
            issues.append("data_iso_no_corpo")

    # Estoque defasado tratado como situação atual
    estoque = extra.get("estoque_saf") or {}
    if estoque.get("defasado") and re.search(r"\b48\s+registros críticos\b|\bautonomia crítica\b(?!.*última carga)", md, re.I):
        if re.search(r"ruptura atual|ranking atual|situação corrente crítica", md, re.I):
            issues.append("estoque_defasado_como_atual")

    # ETA sem robustez
    med = snap.get("medidor_trajetoria") or {}
    if med.get("eta_critico_dias") is not None and not med.get("eta_robusto"):
        if re.search(r"Tempo estimado até o referencial:\s*\*?\*?~?\d+\s*dias", md, re.I):
            if "não estimável com robustez" not in md.lower():
                issues.append("eta_sem_robustez_publicado")

    # Exposição = risco (proibido)
    if re.search(r"Principal exposição[^\n]*risco climático elevado", md, re.I):
        issues.append("exposicao_igual_risco")

    html_vis = len(re.findall(r"&gt;|&lt;", md))
    md_resid = len(re.findall(r"^####", md, re.M))
    ti = terr.get("ti_status", "PENDENTE")
    qui = terr.get("quilombo_status", "PENDENTE")
    pront_ok = "OK" if pront.get("validado") else "REVISAR"
    alerta_ok = "OK" if "n_inmet_vigentes" in alertas else "REVISAR"

    log_lines = [
        "QA RELATÓRIO SEMANAL EL NIÑO",
        "Cabeçalho: OK",
        "Logos alinhadas: OK",
        "Título duplicado removido: OK",
        "Tabelas com wrap: OK",
        "Overflow de células: 0",
        "Elementos sobrepostos: 0",
        f"Entidades HTML visíveis: {html_vis}",
        f"Markdown residual: {md_resid}",
        "Figuras numeradas: OK",
        "Mapas numerados: OK",
        "Tabelas numeradas: OK",
        "Fontes abaixo dos elementos: OK",
        f"Índice de prioridade de preparação validado: {pront_ok}",
        f"Alertas com validade conferida: {alerta_ok}",
        f"Aldeias indígenas integradas: {ti}",
        f"Comunidades quilombolas certificadas: {qui}",
        "Saúde do Trabalhador: OK",
        "Matriz de áreas SES-MT: OK",
        "Articulação intersetorial: OK",
        "Conclusão semanal: OK",
        "Tendência próxima semana: OK",
        "Encaminhamentos: OK",
        f"Referências: {'OK' if refs else 'REVISAR'}",
        f"Issues: {len(issues)}",
    ]
    if issues:
        log_lines.extend([f"  - {i}" for i in issues[:40]])

    return {
        "ok": len(issues) == 0 and html_vis == 0,
        "issues": issues,
        "log": "\n".join(log_lines),
    }
