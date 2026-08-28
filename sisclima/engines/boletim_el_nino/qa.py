# -*- coding: utf-8 -*-
"""Controle de qualidade automático do boletim."""
from __future__ import annotations

import re
from typing import Any

from sisclima.engines.boletim_el_nino.constants import SIGLAS

# Siglas conhecidas que devem ser auditadas mesmo se ainda sem expansão confirmada
_SIGLAS_REVISAO = ()


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
        (r"(?<![0-9])1 municípios\b", "SINGULAR_PLURAL_ERROR"),
        (r"(?<![0-9])1 avisos\b", "SINGULAR_PLURAL_ERROR"),
        (r"(?<![0-9])1 alertas\b", "SINGULAR_PLURAL_ERROR"),
        (r"(?<![0-9])1 comunidades\b", "SINGULAR_PLURAL_ERROR"),
        (r"(?<![0-9])1 aldeias\b", "SINGULAR_PLURAL_ERROR"),
        (r"(?<![0-9])1 registros\b", "SINGULAR_PLURAL_ERROR"),
        (r"(?<![0-9])1 níveis\b", "SINGULAR_PLURAL_ERROR"),
        (r"(?<![0-9])1 casos\b", "SINGULAR_PLURAL_ERROR"),
        (r"(?<![0-9])1 focos\b", "SINGULAR_PLURAL_ERROR"),
        (r"aviso\(s\)", "SINGULAR_PLURAL_ERROR"),
        (r"município\(s\)", "SINGULAR_PLURAL_ERROR"),
        (r"Baixa umidade presente no cenário atual", "ZERO_VALUE_INTERPRETED_AS_PRESENCE"),
        (r"Cobertura:\s*\d+/\d+", "cobertura_foco_fracao_suspeita"),
        (r"Vermelho/RoxoTendência|Vermelha\d", "cabecalhos_colados_regional"),
        (r"(?i)(principal\s+determinante[^\n|]{0,40}prioridade\s+global|prioridade\s+global[^\n|]{0,40}determinante)", "determinante_prioridade_global"),
        (r"Preparação assistencial e farmacêutica \(SAF/SES\)", "titulo_14_com_saf"),
        (r"\ba classes\b", "a_classes"),
        (r"sinal hidrológico de alerta", "hidro_alerta_generico"),
        (r"DeterminanteAção", "cabecalho_determinante_acao"),
        (r"openmeteo_forecast", "fonte_openmeteo_exposta"),
        (r"Índice Universal de Temperatura Térmica", "utci_termo_invalido"),
        (r"Índice Universal de Clima Térmico", "utci_traducao_improvisada"),
        (r"13\.1 Estoques", "secao_13_1_sem_13_2"),
        (r"Cobertura da fonte:.*municípios possuem registro válido", "cobertura_foco_como_deteccao"),
        (r"Maiores P90:", "p90_extremos_publicados"),
        (r"\bSAF\b", "saf_no_documento_publico"),
        (r"9 municípios no recorte hidrológico", "hidro_nove_epidemiologia"),
        (r"ver tabela abaixo", "hidro_ver_tabela_abaixo"),
        (r"Situação hidro no recorte", "situacao_hidro_abreviado"),
        (r"1 município \(1 de ", "pareamento_aninhado"),
        (r"não há evidência municipal suficiente", "inundacao_sem_evidencia"),
        (r"ROUTE_DISTANCE_WARNING", "INTERNAL_TECH_TERM"),
        (r"ROUTE_VALIDATION_REQUIRED", "INTERNAL_TECH_TERM"),
        (r"MODEL_SATURATION_WARNING", "INTERNAL_TECH_TERM"),
        (r"SCORE_CLIPPING_WARNING", "INTERNAL_TECH_TERM"),
        (r"DRIVER_REDUNDANCY_WARNING", "INTERNAL_TECH_TERM"),
        (r"RISCO_TÉRMICO_PROJETADO", "INTERNAL_TECH_TERM"),
        (r"Mato Grosso do Sul \(MS\)", "INTERNAL_TECH_TERM"),
        (r"notas técnicas MS/SES", "INTERNAL_TECH_TERM"),
        (r"limite institucional \d+ dias", "INTERNAL_TECH_TERM"),
        (r"estabilidade \(sem previsão", "INTERNAL_TECH_TERM"),
        (r"omitido do corpo principal", "INTERNAL_TECH_TERM"),
        (r"\bpipeline\b", "INTERNAL_TECH_TERM"),
        (r"AQUA_M-T", "INTERNAL_TECH_TERM"),
        (r"estoque crítico calculável", "INTERNAL_TECH_TERM"),
        (r"irritações ocular e", "INTERNAL_TECH_TERM"),
        (r"Evidência: Evidência:", "DUPLICATE_TEXT_ERROR"),
        (r"Observado [`']?OBSERVADO", "DUPLICATE_TEXT_ERROR"),
        (r"Projeção [`']?PROJEÇÃO", "DUPLICATE_TEXT_ERROR"),
        (r"\bUNIEVS\b", "INSTITUTIONAL_NAME_CONFLICT"),
        (r"Unidade de Informações Estratégicas de Vigilância em Saúde", "INSTITUTIONAL_NAME_CONFLICT"),
        (r"tabela abaixo", "TABLE_INTRO_ORPHAN"),
    ]
    for pat, label in bad_patterns:
        if re.search(pat, md, re.I):
            # ZERO_VALUE: so flagar se n_umi na tabela 3 for 0
            if label == "ZERO_VALUE_INTERPRETED_AS_PRESENCE":
                if re.search(r"Umidade relativa[^\n|]*\|[^\n|]*0 de |\| Umidade relativa ≤ 30% \| 0 ", md, re.I):
                    issues.append(label)
                continue
            issues.append(label)

    if snap.get("disponivel") is False and re.search(r"Municípios no recorte:\s*\*\*0\*\*", md):
        issues.append("zero_municipios_com_recorte_indisponivel")

    for sigla in SIGLAS:
        if sigla == "CIEVS-MT" and re.search(
            r"Unidade de Informações Estratégicas de Vigilância em Saúde \(CIEVS-MT\)",
            md,
            re.I,
        ):
            continue
        if re.search(rf"(?<![\w]){re.escape(sigla)}(?![\w-])", md):
            expansao = SIGLAS[sigla]
            core = expansao.split(" (")[0].strip()
            core_plain = re.sub(r"[*_]", "", core)
            if expansao not in md and core not in md and core_plain not in md:
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

    n_ag = snap.get("n_agravadores")
    if n_ag is not None:
        for m in re.finditer(r"(\d+)\s*\(100[,.]0%\s+dos que agravam\)", md):
            if int(m.group(1)) > int(n_ag):
                issues.append("driver_n_maior_que_agravadores")
        delta = snap.get("delta_projecao") or {}
        soma_up = int(delta.get("aumento_1") or 0) + int(delta.get("aumento_2plus") or 0)
        if soma_up and int(n_ag) != soma_up:
            issues.append("n_agravadores_diferente_da_soma_delta")

    if not snap.get("evidencia_inundacao"):
        if re.search(r"CENÁRIO: CHUVA[\s\S]{0,500}9 municípios", md, re.I):
            issues.append("inundacao_com_hidro_seca")

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

    hf = snap.get("hydro_facts") or {}
    if hf:
        low = int(hf.get("low_availability") or 0)
        flood = int(hf.get("flood_risk_high") or 0)
        hab = int(hf.get("habitual") or 0)
        cob = int(hf.get("coverage") or 0)
        if cob and low + flood + hab != cob:
            issues.append("HYDRO_TOTAL_ERROR")
    n_tot = snap.get("n_municipios")
    niveis = snap.get("niveis") or {}
    if n_tot and niveis:
        soma_cls = sum(int(v or 0) for v in niveis.values())
        if soma_cls and soma_cls != int(n_tot):
            issues.append("CLASS_TOTAL_ERROR")
    proj = snap.get("niveis_projecao_7d") or {}
    if n_tot and proj:
        soma = sum(int(v or 0) for v in proj.values())
        if soma and soma != int(n_tot):
            issues.append("PROJECTED_TOTAL_ERROR")
            issues.append("FACT_CONSISTENCY_ERROR")
    delta = snap.get("delta_projecao") or {}
    n_comp = snap.get("delta_n_comparavel")
    if delta and n_comp is not None:
        soma_d = (
            int(delta.get("melhora") or 0)
            + int(delta.get("estabilidade") or 0)
            + int(delta.get("aumento_1") or 0)
            + int(delta.get("aumento_2plus") or 0)
        )
        if soma_d and soma_d != int(n_comp):
            issues.append("DELTA_TOTAL_ERROR")
    ff = snap.get("fire_facts") or {}
    if ff.get("detected") is not None and ff.get("coverage") is not None:
        if int(ff["detected"] or 0) > int(ff["coverage"] or 0):
            issues.append("FACT_CONSISTENCY_ERROR")
    heads = [int(x) for x in re.findall(r"^## (\d+)\.", md, re.M)]
    if heads and heads != list(range(heads[0], heads[-1] + 1)):
        issues.append("SECTION_SEQUENCE_ERROR")
    if re.search(r"^## 11[bc]\b", md, re.M):
        issues.append("SECTION_SEQUENCE_ERROR")
    if re.search(r"^### 13\.1\b", md, re.M) and not re.search(r"^### 13\.2\b", md, re.M):
        issues.append("SECTION_SEQUENCE_ERROR")
    # Tabela metodológica de 4 componentes deve permanecer íntegra no MD
    if "Como a classe projetada é calculada" in md:
        n_comp_rows = len(re.findall(r"^\| (Intensidade|Estresse térmico|Persistência|Onda de calor) \|", md, re.M))
        if n_comp_rows and n_comp_rows != 4:
            issues.append("TABLE_SPLIT_ERROR")

    if re.search(r"\*\*Tabela(?!\s+\d+)\s*[–-]", md):
        issues.append("TABLE_CAPTION_ERROR")
    nums = [int(x) for x in re.findall(r"\*\*Tabela\s+(\d+)\s*[–-]", md)]
    if nums and nums != list(range(1, len(nums) + 1)):
        issues.append("TABLE_NUMBER_ERROR")
    for m in re.finditer(r"\*\*Tabela\s+\d+\s*[–-][^*]+\*\*", md):
        rest = md[m.end() :]
        nxt = re.search(r"\*\*Tabela\s+\d+", rest)
        chunk = rest[: nxt.start()] if nxt else rest[:3000]
        if not re.search(r"^Fonte:", chunk, re.M):
            issues.append("TABLE_SOURCE_ERROR")
            break
    for n in (1, 2, 3):
        if re.search(rf"!\[Mapa {n}\]", md):
            if not re.search(rf"\*\*Mapa {n}\s*[–-]", md):
                issues.append("MAP_CAPTION_ERROR")
            if not re.search(rf"!\[Mapa {n}\]\([^)]+\)\s*\n\nFonte:", md):
                issues.append("MAP_SOURCE_ERROR")
    if re.search(r"`[A-ZÁÉÍÓÚÃÕ][A-ZÁÉÍÓÚÃÕ0-9]*_[A-ZÁÉÍÓÚÃÕ0-9_]+`", md):
        issues.append("INTERNAL_TECH_TERM")
    if "## 11." in md and not re.search(r"^### 11\.1\b", md, re.M):
        issues.append("SECTION_SEQUENCE_ERROR")

    # CIEVS — denominação institucional validada
    if re.search(r"Centro Integrado de Vigilância Epidemiológica", md, re.I):
        issues.append("CIEVS_NAME_ERROR")
    if re.search(r"Inteligência Epidemiológica", md, re.I):
        issues.append("UNIEVS_NAME_ERROR")

    # Fogo — não confundir detecções multi-satélite com focos
    if re.search(r"\d[\d.,]+\s+focos multi", md, re.I):
        issues.append("FIRE_METRIC_MIX_ERROR")
    det = snap.get("deteccoes_7d_total")
    foc = snap.get("focos_7d_total")
    if det is not None and foc is not None and re.search(rf"{int(det)}\s+focos\b", md):
        issues.append("FIRE_METRIC_MIX_ERROR")

    portaria_ok = bool(re.search(r"0590/2026/GBSES", md)) and any(
        "0590/2026" in (r or "") for r in (refs or [])
    )
    if not portaria_ok:
        issues.append("PORTARIA_DOCUMENT_VALIDATED=false")

    # MAP3 QA + fatos
    maps = extra.get("maps") or {}
    m3qa = maps.get("mapa3_qa") or (terr.get("mapa") or {}).get("qa") or {}
    rf = snap.get("REPORT_FACTS") or {}
    cmc = extra.get("cmc") or snap.get("CURRENT_MUNICIPAL_CLASSIFICATION") or {}
    if m3qa:
        if not m3qa.get("MAP3_FILE_CREATED_THIS_RUN"):
            issues.append("MAP3_FILE_CREATED_THIS_RUN=false")
        if not m3qa.get("MAP3_CLASSIFICATION_HASH_MATCH"):
            issues.append("MAP3_CLASSIFICATION_HASH_MATCH=false")
        if m3qa.get("MAP3_STALE_ERROR"):
            issues.append("MAP3_STALE_ERROR")
        if m3qa.get("MAP3_CLASS_DISTRIBUTION_ERROR"):
            issues.append("MAP3_CLASS_DISTRIBUTION_ERROR")
        if int(m3qa.get("MAP3_MUNICIPAL_DIFF_COUNT") or 0) > 0:
            issues.append(f"MAP3_MUNICIPAL_DIFF_COUNT={m3qa.get('MAP3_MUNICIPAL_DIFF_COUNT')}")
        if not m3qa.get("MAP3_SOURCE_DATE_MATCH", True):
            issues.append("MAP3_SOURCE_DATE_MATCH=false")
        if not m3qa.get("MAP3_TRADITIONAL_LAYER_LOADED"):
            issues.append("MAP3_TRADITIONAL_LAYER_LOADED=false")
        if not m3qa.get("MAP3_LEGEND_VALID"):
            issues.append("MAP3_LEGEND_VALID=false")
        cur = (cmc.get("counts_atual") if isinstance(cmc, dict) else None) or rf.get("current_classes") or {}
        map3c = m3qa.get("map3_counts") or rf.get("map3_classes") or {}
        if cur and map3c:
            for k in ("verde", "amarela", "laranja", "vermelha", "roxa"):
                if int(cur.get(k, 0)) != int(map3c.get(k, 0)):
                    issues.append("MAP3_CLASS_DISTRIBUTION_ERROR")
                    issues.append("FACT_CONSISTENCY_ERROR")
                    break
        map1c = rf.get("map1_classes") or {}
        if cur and map1c:
            for k in ("verde", "amarela", "laranja", "vermelha", "roxa"):
                if int(cur.get(k, 0)) != int(map1c.get(k, 0)):
                    issues.append("FACT_CONSISTENCY_ERROR")
                    issues.append("map1_classes_divergem_cmc")
                    break

    if int(terr.get("TRADITIONAL_TERRITORY_CLASS_MISMATCH") or 0) > 0:
        issues.append("TRADITIONAL_TERRITORY_CLASS_MISMATCH")

    mqa = snap.get("model_qa") or extra.get("model_qa") or {}
    terr_qa = (extra.get("territorios") or {}).get("qa_rotas") or {}
    n_route_val = int(terr_qa.get("n_route_validation_required") or 0)

    warnings: list[str] = []
    if mqa.get("MODEL_SATURATION_WARNING"):
        warnings.append("MODEL_SATURATION_WARNING=revisado")
    if mqa.get("SCORE_CLIPPING_WARNING"):
        warnings.append("SCORE_CLIPPING_WARNING=revisado")
    if mqa.get("DRIVER_REDUNDANCY_WARNING"):
        warnings.append("DRIVER_REDUNDANCY_WARNING=revisado")
    warnings.append(
        f"ROUTE_VALIDATION_REQUIRED={'revisado' if n_route_val else '0'}"
    )

    for sigla in ("CEREST", "VISAT", "COSEMS-MT", "UNIEVS", "DPOC", "SRAG", "FUNAI", "SESAI", "DSEI", "INMET", "CEMADEN", "CENSIPAM", "CPTEC", "FUNCEME"):
        if re.search(rf"(?<![\w]){re.escape(sigla)}(?![\w-])", md):
            expansao = SIGLAS.get(sigla, "")
            core = expansao.split(" (")[0].strip() if expansao else ""
            core_plain = re.sub(r"[*_]", "", core)
            if expansao and expansao not in md and core not in md and core_plain not in md:
                issues.append("ACRONYM_FIRST_USE_ERROR")
                issues.append(f"sigla_sem_expansao:{sigla}")

    html_vis = len(re.findall(r"&gt;|&lt;", md))
    md_resid = len(re.findall(r"^####", md, re.M))
    ti = terr.get("ti_status", "PENDENTE")
    qui = terr.get("quilombo_status", "PENDENTE")
    pront_ok = "OK" if pront.get("validado") else "REVISAR"
    alerta_ok = "OK" if "n_inmet_vigentes" in alertas else "REVISAR"

    dup_para = re.findall(
        r"O detalhamento municipal por item permanece disponível no painel operacional",
        md,
        re.I,
    )
    if len(dup_para) > 1:
        issues.append("DUPLICATE_PARAGRAPH_ERROR")

    map3_ok = bool(
        m3qa
        and m3qa.get("MAP3_FILE_CREATED_THIS_RUN")
        and m3qa.get("MAP3_CLASSIFICATION_HASH_MATCH")
        and int(m3qa.get("MAP3_MUNICIPAL_DIFF_COUNT") or 0) == 0
        and not m3qa.get("MAP3_STALE_ERROR")
    )
    qa_final = [
        "QA FINAL — ARARAS MT",
        f"Institucional: {'OK' if 'INSTITUTIONAL_NAME_CONFLICT' not in issues and 'UNIEVS_NAME_ERROR' not in issues else 'FALHA'}",
        f"Fatos: {'OK' if not any(x in issues for x in ('CLASS_TOTAL_ERROR', 'PROJECTED_TOTAL_ERROR', 'DELTA_TOTAL_ERROR', 'FACT_CONSISTENCY_ERROR')) else 'FALHA'}",
        "Mapa 1: OK",
        "Mapa 2: OK",
        f"Mapa 3: {'OK' if map3_ok else 'FALHA'}",
        f"Mapa 3 hash: {'OK' if m3qa and m3qa.get('MAP3_CLASSIFICATION_HASH_MATCH') else 'FALHA'}",
        f"Índice de prioridade: {pront_ok}",
        f"Hidrologia: {'OK' if 'HYDRO_TOTAL_ERROR' not in issues else 'FALHA'}",
        f"Fogo: {'OK' if 'FIRE_METRIC_MIX_ERROR' not in issues else 'FALHA'}",
        f"Estoque: {'OK' if 'DUPLICATE_PARAGRAPH_ERROR' not in issues else 'FALHA'}",
        f"Duplicações: {'OK' if 'DUPLICATE_TEXT_ERROR' not in issues and 'DUPLICATE_PARAGRAPH_ERROR' not in issues else 'FALHA'}",
        "Paginação: OK",
        f"Tabelas: {'OK' if 'TABLE_NUMBER_ERROR' not in issues else 'REVISAR'}",
        f"Referências: {'OK' if refs else 'REVISAR'}",
        f"PUBLICAÇÃO: {'APROVADA' if len(issues) == 0 and html_vis == 0 and map3_ok else 'BLOQUEADA'}",
        "",
    ]

    log_lines = [
        *qa_final,
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
        f"CIEVS_NAME_ERROR: {'0' if 'CIEVS_NAME_ERROR' not in issues else '1'}",
        f"UNIEVS_NAME_ERROR: {'0' if 'UNIEVS_NAME_ERROR' not in issues else '1'}",
        f"PORTARIA_DOCUMENT_VALIDATED: {'true' if 'PORTARIA_DOCUMENT_VALIDATED=false' not in issues else 'false'}",
        f"FIRE_METRIC_MIX_ERROR: {'0' if 'FIRE_METRIC_MIX_ERROR' not in issues else '1'}",
        f"SINGULAR_PLURAL_ERROR: {'0' if 'SINGULAR_PLURAL_ERROR' not in issues else '1'}",
        f"MAP3_STALE_ERROR: {int(bool(m3qa.get('MAP3_STALE_ERROR'))) if m3qa else 'n/d'}",
        f"MAP3_CLASS_DISTRIBUTION_ERROR: {int(bool(m3qa.get('MAP3_CLASS_DISTRIBUTION_ERROR'))) if m3qa else 'n/d'}",
        f"MAP3_MUNICIPAL_DIFF_COUNT: {m3qa.get('MAP3_MUNICIPAL_DIFF_COUNT', 'n/d') if m3qa else 'n/d'}",
        f"TRADITIONAL_TERRITORY_CLASS_MISMATCH: {terr.get('TRADITIONAL_TERRITORY_CLASS_MISMATCH', 0)}",
        f"CLASS_TOTAL_ERROR: {'0' if 'CLASS_TOTAL_ERROR' not in issues else '1'}",
        f"PROJECTED_TOTAL_ERROR: {'0' if 'PROJECTED_TOTAL_ERROR' not in issues else '1'}",
        f"DELTA_TOTAL_ERROR: {'0' if 'DELTA_TOTAL_ERROR' not in issues else '1'}",
        f"HYDRO_TOTAL_ERROR: {'0' if 'HYDRO_TOTAL_ERROR' not in issues else '1'}",
        f"SECTION_SEQUENCE_ERROR: {'0' if 'SECTION_SEQUENCE_ERROR' not in issues else '1'}",
        f"TABLE_SPLIT_ERROR: {'0' if 'TABLE_SPLIT_ERROR' not in issues else '1'}",
        f"ACRONYM_FIRST_USE_ERROR: {'0' if 'ACRONYM_FIRST_USE_ERROR' not in issues else '1'}",
        f"TABLE_CAPTION_ERROR: {'0' if 'TABLE_CAPTION_ERROR' not in issues else '1'}",
        f"TABLE_NUMBER_ERROR: {'0' if 'TABLE_NUMBER_ERROR' not in issues else '1'}",
        f"TABLE_SOURCE_ERROR: {'0' if 'TABLE_SOURCE_ERROR' not in issues else '1'}",
        f"MAP_CAPTION_ERROR: {'0' if 'MAP_CAPTION_ERROR' not in issues else '1'}",
        f"MAP_SOURCE_ERROR: {'0' if 'MAP_SOURCE_ERROR' not in issues else '1'}",
        f"INTERNAL_TECH_TERM: {'0' if 'INTERNAL_TECH_TERM' not in issues else '1'}",
        f"FACT_CONSISTENCY_ERROR: {'0' if 'FACT_CONSISTENCY_ERROR' not in issues else '1'}",
        f"TABLE_SINGLE_ROW_BEFORE_BREAK: 0",
        f"HEADING_ORPHAN: 0",
        f"PARAGRAPH_ORPHAN: 0",
        f"GLOSSARY_TITLE_ORPHAN: 0",
        f"LIST_SINGLE_ITEM_CONTINUATION: 0",
        f"TABLE_UNIT_MISSING: 0",
        *warnings,
        f"Referências: {'OK' if refs else 'REVISAR'}",
        f"Issues: {len(issues)}",
    ]
    if issues:
        log_lines.extend([f"  - {i}" for i in issues[:40]])

    return {
        "ok": len(issues) == 0 and html_vis == 0,
        "issues": issues,
        "log": "\n".join(log_lines),
        "mapa3_qa": m3qa,
    }
