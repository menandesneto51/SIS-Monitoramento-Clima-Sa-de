# -*- coding: utf-8 -*-
"""Importa Matriz Plano de Ação Revisada → atualiza catálogo mantendo 88 IND-* oficiais."""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sisclima.plano.areas import area_id_de_responsavel  # noqa: E402
from sisclima.plano.constants import MAPA_MODO_PLANILHA, MAPA_TIPO_PLANILHA  # noqa: E402

DEFAULT_NEW = Path.home() / "Downloads" / "Matriz Plano de Ação_Revisada.xlsx"
DEFAULT_OLD = Path.home() / "Downloads" / "Controle_Indicacoes_El_Nino_SES_MT_2026.xlsx"
CATALOGO_BASE = ROOT / "config" / "_catalogo_anterior_backup.yaml"
CATALOGO_OUT = ROOT / "config" / "plano_el_nino_2026_catalogo.yaml"
MATRIZ_OUT = ROOT / "config" / "plano_el_nino_matriz.yaml"
DIFF_OUT = ROOT / "docs" / "apresentacoes" / "diff_indicadores_plano_el_nino_revisada.md"
TARGET_N = 88
MATCH_MIN = 0.28
MATCH_MIN_PROTEGIDO = 0.40

# IDs com coletor/escalonamento amarrado — só mudam nome com match forte.
IDS_PROTEGIDOS = frozenset(
    {
        "IND-001",
        "IND-003",
        "IND-004",
        "IND-005",
        "IND-006",
        "IND-007",
        "IND-008",
        "IND-011",
        "IND-012",
        "IND-013",
        "IND-015",
        "IND-016",
        "IND-018",
        "IND-019",
        "IND-021",
        "IND-023",
        "IND-024",
        "IND-025",
        "IND-029",
        "IND-030",
        "IND-032",
        "IND-052",
        "IND-053",
        "IND-058",
        "IND-059",
        "IND-060",
        "IND-061",
        "IND-062",
        "IND-063",
        "IND-064",
        "IND-066",
        "IND-067",
        "IND-068",
        "IND-069",
        "IND-070",
        "IND-072",
        "IND-073",
        "IND-074",
        "IND-075",
        "IND-076",
        "IND-077",
        "IND-079",
        "IND-083",
        "IND-086",
    }
)


def fold(texto: str) -> str:
    txt = unicodedata.normalize("NFKD", str(texto or ""))
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", txt).strip().casefold()


def slug(texto: str, prefixo: str = "") -> str:
    base = fold(texto)
    base = re.sub(r"[^a-z0-9]+", "_", base).strip("_")[:60]
    return f"{prefixo}{base}" if prefixo else base


def tipo_de(valor: str) -> str:
    t = fold(valor).replace(" ", "")
    return MAPA_TIPO_PLANILHA.get(t, "execucao")


def modo_de(valor: str) -> str:
    t = fold(valor).replace(" ", "")
    if t in MAPA_MODO_PLANILHA:
        return MAPA_MODO_PLANILHA[t]
    if "semi" in t:
        return "semiautomatico"
    if "manual" in t:
        return "documental"
    if "auto" in t:
        return "automatico"
    return "documental"


def split_indicadores(texto: str) -> list[str]:
    raw = str(texto or "").strip()
    if not raw or raw.lower() == "nan":
        return []
    parts = [p.strip(" -\t") for p in re.split(r"[;\n]+", raw) if p.strip(" -\t")]
    out: list[str] = []
    for p in parts:
        if p.count("%") >= 2 and " e " in p.casefold():
            bits = re.split(r"\s+e\s+", p, flags=re.I)
            out.extend(b.strip(" ,;") for b in bits if b.strip(" ,;"))
        else:
            out.append(p)
    return out or [raw]


def infer_tipo_ind(texto: str) -> str:
    t = fold(texto)
    if any(k in t for k in ("risco", "alerta", "gatilho", "limiar", "anomalia")):
        return "risco_gatilho"
    if any(k in t for k in ("capacidade", "prontidao", "estoque", "plano de conting", "protocolo")):
        return "capacidade"
    if any(k in t for k in ("reducao", "queda", "latencia", "cobertura atingida", "resultado", "obito", "internac")):
        return "resultado"
    return "execucao"


def infer_modo(texto: str, responsavel: str) -> str:
    t = fold(texto + " " + responsavel)
    if any(k in t for k in ("sinan", "sisagua", "cnes", "open-meteo", "pm2", "foco", "dw", "automatic")):
        return "automatico"
    if any(k in t for k in ("monitor", "percent", "%", "cobertura", "estoque")):
        return "semiautomatico"
    return "documental"


def ler_acoes_revisadas(path: Path) -> list[dict]:
    df = pd.read_excel(path, sheet_name="Ações e indicadores", header=1)
    df["SETOR/EIXO"] = df["SETOR/EIXO"].ffill()
    df = df.dropna(subset=["Ação"])
    acoes = []
    for i, r in df.iterrows():
        acao = str(r.get("Ação") or "").strip()
        if not acao or acao.lower() == "nan":
            continue
        eixo = str(r.get("SETOR/EIXO") or "Sem eixo").strip()
        if eixo.lower() == "nan":
            eixo = "Sem eixo"
        ind_raw = str(r.get("Indicador de monitoramento") or "").strip()
        fragments = split_indicadores(ind_raw)
        acoes.append(
            {
                "linha": int(i) + 1,
                "eixo": eixo,
                "acao": acao,
                "meta": str(r.get("Meta") or "").strip(),
                "responsavel": str(r.get("Responsável") or "").strip(),
                "prazo": str(r.get("Prazo") or "").strip(),
                "prioridade": str(r.get("Prioridade") or "Alta").strip(),
                "status": str(r.get("Status inicial") or "A validar").strip(),
                "indicador_original": ind_raw if ind_raw.lower() != "nan" else "",
                "fragments": fragments if fragments else ([acao[:120] + " — evidência documental"]),
            }
        )
    return acoes


def carregar_arara_antiga(path: Path) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name="Matriz_ARARA")


def match_score(a: str, b: str) -> float:
    fa, fb = set(fold(a).split()), set(fold(b).split())
    if not fa or not fb:
        return 0.0
    return len(fa & fb) / len(fa | fb)


def expandir_conteudos(acoes: list[dict], antiga: pd.DataFrame) -> list[dict]:
    """Pool de conteúdos (pode ser >88); depois o merge fixa em 88 IND oficiais."""
    novos: list[dict] = []
    for ac in acoes:
        for frag in ac["fragments"]:
            novos.append(
                {
                    "eixo": ac["eixo"],
                    "meta": ac["meta"],
                    "acao": ac["acao"],
                    "responsavel": ac["responsavel"],
                    "prazo": ac["prazo"],
                    "prioridade": ac["prioridade"],
                    "status": ac["status"],
                    "indicador_original": ac["indicador_original"],
                    "indicador": frag,
                    "tipo": infer_tipo_ind(frag),
                    "modo": infer_modo(frag, ac["responsavel"]),
                    "origem": "revisada",
                    "linha_revisada": ac["linha"],
                }
            )

    usados = {fold(x["indicador"]) for x in novos}
    complementos: list[tuple[float, dict]] = []
    for _, r in antiga.iterrows():
        prop = str(r.get("Indicador ARARA proposto") or "").strip()
        if not prop or fold(prop) in usados:
            continue
        best = max((match_score(prop, a["acao"]) for a in acoes), default=0.0)
        best_acao = max(acoes, key=lambda a: match_score(prop, a["acao"])) if acoes else None
        if best < 0.12:
            continue
        complementos.append(
            (
                best,
                {
                    "eixo": str(r.get("Eixo") or (best_acao or {}).get("eixo") or ""),
                    "meta": str(r.get("Meta original") or (best_acao or {}).get("meta") or ""),
                    "acao": str((best_acao or {}).get("acao") or r.get("Ação original") or ""),
                    "responsavel": str((best_acao or {}).get("responsavel") or r.get("Responsável") or ""),
                    "prazo": str((best_acao or {}).get("prazo") or r.get("Prazo original") or ""),
                    "prioridade": str((best_acao or {}).get("prioridade") or r.get("Prioridade") or "Alta"),
                    "status": str((best_acao or {}).get("status") or r.get("Status original") or "A validar"),
                    "indicador_original": str(r.get("Indicador original") or ""),
                    "indicador": prop,
                    "tipo": tipo_de(str(r.get("Tipo") or "Execução")),
                    "modo": modo_de(str(r.get("Automação") or "Semiautomático")),
                    "origem": "legado_alinhado",
                    "linha_revisada": (best_acao or {}).get("linha"),
                    "codigo_legado": str(r.get("ID ARARA") or ""),
                    "formula": str(r.get("Fórmula / regra de cálculo") or ""),
                    "meta_gatilho": str(r.get("Meta / gatilho") or ""),
                    "unidade": str(r.get("Unidade") or ""),
                    "direcao": str(r.get("Direção") or ""),
                    "fonte": str(r.get("Fonte primária sugerida") or ""),
                    "periodicidade": str(r.get("Periodicidade") or ""),
                    "semaforo": str(r.get("Regra de semáforo / gatilho") or ""),
                    "evidencia": str(r.get("Evidência mínima") or ""),
                },
            )
        )
    complementos.sort(key=lambda x: x[0], reverse=True)
    for _, item in complementos:
        if fold(item["indicador"]) in usados:
            continue
        usados.add(fold(item["indicador"]))
        novos.append(item)

    for _, r in antiga.iterrows():
        prop = str(r.get("Indicador ARARA proposto") or "").strip()
        if not prop or fold(prop) in usados:
            continue
        usados.add(fold(prop))
        novos.append(
            {
                "eixo": str(r.get("Eixo") or ""),
                "meta": str(r.get("Meta original") or ""),
                "acao": str(r.get("Ação original") or ""),
                "responsavel": str(r.get("Responsável") or ""),
                "prazo": str(r.get("Prazo original") or ""),
                "prioridade": str(r.get("Prioridade") or "Alta"),
                "status": str(r.get("Status original") or "A validar"),
                "indicador_original": str(r.get("Indicador original") or ""),
                "indicador": prop,
                "tipo": tipo_de(str(r.get("Tipo") or "Execução")),
                "modo": modo_de(str(r.get("Automação") or "Semiautomático")),
                "origem": "legado_complementar",
                "codigo_legado": str(r.get("ID ARARA") or ""),
                "formula": str(r.get("Fórmula / regra de cálculo") or ""),
                "meta_gatilho": str(r.get("Meta / gatilho") or ""),
                "unidade": str(r.get("Unidade") or ""),
                "direcao": str(r.get("Direção") or ""),
                "fonte": str(r.get("Fonte primária sugerida") or ""),
                "periodicidade": str(r.get("Periodicidade") or ""),
                "semaforo": str(r.get("Regra de semáforo / gatilho") or ""),
                "evidencia": str(r.get("Evidência mínima") or ""),
            }
        )
    return novos


def _parear_greedy(
    base: list[dict],
    conteudos: list[dict],
    *,
    usados_i: set[int] | None = None,
    usados_j: set[int] | None = None,
    min_score: float = MATCH_MIN,
    bonus_codigo: bool = False,
) -> list[tuple[int, int, float]]:
    """Emparelha índices base↔conteúdo por melhor Jaccard, sem reutilizar slots."""
    usados_i = set(usados_i or ())
    usados_j = set(usados_j or ())
    pares: list[tuple[float, int, int]] = []
    for i, old in enumerate(base):
        if i in usados_i:
            continue
        for j, novo in enumerate(conteudos):
            if j in usados_j:
                continue
            s = match_score(old.get("nome") or "", novo.get("indicador") or "")
            if bonus_codigo:
                cod = str(novo.get("codigo_legado") or "").strip()
                if cod and cod == str(old.get("codigo_fonte") or "").strip():
                    s = max(s, 0.95)
            if s >= min_score:
                pares.append((s, i, j))
    pares.sort(reverse=True)
    out: list[tuple[int, int, float]] = []
    for s, i, j in pares:
        if i in usados_i or j in usados_j:
            continue
        usados_i.add(i)
        usados_j.add(j)
        out.append((i, j, s))
    return out


def mesclar_mantendo_ind(
    catalogo_base: dict,
    acoes_rev: list[dict],
    conteudos: list[dict],
    fonte_xlsx: str,
) -> tuple[dict, list[dict], list[dict], list[dict]]:
    """Atualiza nomes/ações da planilha revisada preservando id IND-* e codigo_fonte ARARA-*."""
    base_inds = [dict(x) for x in (catalogo_base.get("indicadores") or [])]
    if len(base_inds) != TARGET_N:
        raise SystemExit(f"Catálogo base deve ter {TARGET_N} indicadores, achou {len(base_inds)}")

    # Fase 1: só planilha revisada (não deixa o legado monopolizar os 88 slots)
    # Fase 2: legado nos IND restantes
    rev = [c for c in conteudos if c.get("origem") == "revisada"]
    outros = [c for c in conteudos if c.get("origem") != "revisada"]
    pool = rev + outros
    n_rev = len(rev)

    pares_rev_local = _parear_greedy(base_inds, rev, min_score=MATCH_MIN, bonus_codigo=False)
    pares = [(i, j, s) for i, j, s in pares_rev_local]
    # descarta matches fracos em IDs protegidos
    pares = [
        (i, j, s)
        for i, j, s in pares
        if str(base_inds[i].get("id") or "") not in IDS_PROTEGIDOS or s >= MATCH_MIN_PROTEGIDO
    ]
    usados_i = {i for i, _, _ in pares}
    usados_j = {j for _, j, _ in pares}

    # Fase 2: encaixa revisados restantes em slots NÃO protegidos (pareamento guloso global)
    pend_rev = [j for j in range(len(rev)) if j not in usados_j]
    livres_pref = [
        i
        for i in range(len(base_inds))
        if i not in usados_i and str(base_inds[i].get("id") or "") not in IDS_PROTEGIDOS
    ]
    cand: list[tuple[float, int, int]] = []
    for j in pend_rev:
        novo = rev[j]
        for i in livres_pref:
            s = match_score(base_inds[i].get("nome") or "", novo.get("indicador") or "")
            s = max(s, 0.55 * match_score(base_inds[i].get("nome") or "", novo.get("acao") or ""))
            if s >= 0.15:
                cand.append((s, i, j))
    cand.sort(reverse=True)
    for s, i, j in cand:
        if i in usados_i or j in usados_j:
            continue
        usados_i.add(i)
        usados_j.add(j)
        pares.append((i, j, s))

    # Completa slots flexíveis restantes com revisados órfãos (painel reflete a planilha atual)
    livres_pref = [
        i
        for i in range(len(base_inds))
        if i not in usados_i and str(base_inds[i].get("id") or "") not in IDS_PROTEGIDOS
    ]
    pend_rev = [j for j in range(len(rev)) if j not in usados_j]
    for i, j in zip(livres_pref, pend_rev):
        s = match_score(base_inds[i].get("nome") or "", rev[j].get("indicador") or "")
        usados_i.add(i)
        usados_j.add(j)
        pares.append((i, j, max(s, 0.15)))

    # protegidos livres só com match forte residual
    livres_prot = [
        i
        for i in range(len(base_inds))
        if i not in usados_i and str(base_inds[i].get("id") or "") in IDS_PROTEGIDOS
    ]
    pend_rev = [j for j in range(len(rev)) if j not in usados_j]
    cand_p: list[tuple[float, int, int]] = []
    for j in pend_rev:
        novo = rev[j]
        for i in livres_prot:
            s = match_score(base_inds[i].get("nome") or "", novo.get("indicador") or "")
            if s >= MATCH_MIN_PROTEGIDO:
                cand_p.append((s, i, j))
    cand_p.sort(reverse=True)
    for s, i, j in cand_p:
        if i in usados_i or j in usados_j:
            continue
        usados_i.add(i)
        usados_j.add(j)
        pares.append((i, j, s))

    # Fase 3: legado só nos IND que ainda não receberam texto da revisada
    pares_leg = _parear_greedy(
        base_inds,
        pool,
        usados_i=usados_i,
        usados_j=usados_j,
        min_score=0.12,
        bonus_codigo=True,
    )
    pares = pares + pares_leg
    por_base = {i: (j, s) for i, j, s in pares}
    alterados: list[dict] = []

    # Eixos / metas / ações a partir da planilha revisada (estrutura operacional atual)
    eixos_ordem: list[str] = []
    for a in acoes_rev:
        if a["eixo"] not in eixos_ordem:
            eixos_ordem.append(a["eixo"])
    # preservar eixos do catálogo base que ainda existam por nome
    for e in catalogo_base.get("eixos") or []:
        nome = str(e.get("nome") or "")
        if nome and nome not in eixos_ordem:
            eixos_ordem.append(nome)
    eixos = [{"id": slug(n, "eixo_"), "nome": n, "ordem": i + 1} for i, n in enumerate(eixos_ordem)]
    eixo_ids = {e["nome"]: e["id"] for e in eixos}

    areas_seen: dict[str, str] = {}
    areas: list[dict] = []
    for a in catalogo_base.get("areas") or []:
        areas_seen[a["id"]] = a.get("nome") or a["id"]
        areas.append({"id": a["id"], "nome": a.get("nome") or a["id"]})

    metas_seen: dict[tuple[str, str], str] = {}
    metas: list[dict] = []
    acoes_cat: list[dict] = []
    for i, a in enumerate(acoes_rev, start=1):
        area_id = area_id_de_responsavel(a["responsavel"] or a["eixo"])
        if area_id not in areas_seen:
            areas_seen[area_id] = a["responsavel"] or a["eixo"]
            areas.append({"id": area_id, "nome": a["responsavel"] or a["eixo"] or area_id})
        eixo_id = eixo_ids.get(a["eixo"], slug(a["eixo"], "eixo_"))
        chave = (eixo_id, a["meta"])
        if chave not in metas_seen:
            mid = f"M{len(metas_seen)+1:02d}"
            metas_seen[chave] = mid
            metas.append(
                {
                    "id": mid,
                    "eixo_id": eixo_id,
                    "descricao": a["meta"] or f"Meta {mid}",
                    "prazo": a["prazo"] or "",
                }
            )
        acoes_cat.append(
            {
                "id": f"A{i:02d}",
                "meta_id": metas_seen[chave],
                "eixo_id": eixo_id,
                "area_id": area_id,
                "nome": a["acao"],
                "responsavel": a["responsavel"],
                "prazo": a["prazo"],
                "prioridade": a["prioridade"],
                "status_inicial": a["status"],
                "indicador_original": a["indicador_original"],
                "linha_fonte": a["linha"],
            }
        )
    acao_id_by_fold = {fold(a["nome"]): a["id"] for a in acoes_cat}

    inds_out: list[dict] = []
    matriz_rows: list[dict] = []
    for i, old in enumerate(base_inds):
        item = dict(old)
        # garantir contrato oficial
        n = i + 1
        item["id"] = f"IND-{n:03d}"
        item["codigo_fonte"] = item.get("codigo_fonte") or f"ARARA-{n:03d}"
        if not str(item["codigo_fonte"]).startswith("ARARA-"):
            item["codigo_fonte"] = f"ARARA-{n:03d}"

        origem = "legado_preservado"
        score = 0.0
        novo = None
        if i in por_base:
            j, score = por_base[i]
            novo = pool[j]
            nome_novo = str(novo.get("indicador") or "").strip()
            iid = str(item.get("id") or "")
            protegido = iid in IDS_PROTEGIDOS
            limiar = MATCH_MIN_PROTEGIDO if protegido else MATCH_MIN
            # Slots flexíveis (não protegidos) aceitam texto revisado mesmo com score baixo
            aceita_nome = bool(nome_novo) and (
                (not protegido and str(novo.get("origem") or "") == "revisada" and score >= 0.15)
                or score >= limiar
                or str(novo.get("origem") or "") != "revisada"
            )
            if nome_novo and fold(nome_novo) != fold(item.get("nome") or "") and aceita_nome:
                alterados.append(
                    {
                        "id": item["id"],
                        "antes": item.get("nome"),
                        "depois": nome_novo,
                        "score": round(score, 3),
                        "origem": novo.get("origem"),
                    }
                )
                item["nome"] = nome_novo
                item.pop("indicador_revisado_sugerido", None)
                item.pop("match_score_sugerido", None)
            elif nome_novo and fold(nome_novo) != fold(item.get("nome") or ""):
                item["indicador_revisado_sugerido"] = nome_novo
                item["match_score_sugerido"] = round(score, 3)
            if novo.get("formula"):
                item["formula"] = novo["formula"]
            if novo.get("meta_gatilho"):
                item["meta_numerica"] = novo["meta_gatilho"]
            if novo.get("unidade"):
                item["unidade"] = novo["unidade"]
            if novo.get("direcao"):
                item["direcao"] = novo["direcao"]
            if novo.get("fonte"):
                item["fonte"] = novo["fonte"]
            if novo.get("periodicidade"):
                item["periodicidade"] = novo["periodicidade"]
            if novo.get("semaforo"):
                item["semaforo"] = novo["semaforo"]
            if novo.get("evidencia"):
                item["evidencia_minima"] = novo["evidencia"]
            if novo.get("indicador_original"):
                item["indicador_original"] = novo["indicador_original"]
            # tipo/modo: só atualiza se veio da revisada e score alto (não quebra conectores)
            if novo.get("origem") == "revisada" and score >= 0.45:
                # não sobrescreve risco_gatilho / capacidade já tipados no legado operacional
                if item.get("tipo") not in {"risco_gatilho", "capacidade", "resultado"}:
                    item["tipo"] = novo.get("tipo") or item.get("tipo")
            origem = str(novo.get("origem") or "revisada")
            if novo.get("origem") == "revisada" and protegido and score < MATCH_MIN_PROTEGIDO:
                origem = "revisada_sugerida"

            # área / eixo / ação — remapeia em slots flexíveis ou com match suficiente
            if (not protegido and str(novo.get("origem") or "") == "revisada") or score >= limiar or str(
                novo.get("origem") or ""
            ) != "revisada":
                resp = novo.get("responsavel") or ""
                if resp:
                    area_id = area_id_de_responsavel(resp)
                    if area_id not in areas_seen:
                        areas_seen[area_id] = resp
                        areas.append({"id": area_id, "nome": resp})
                    item["area_id"] = area_id
                eixo_nome = novo.get("eixo") or ""
                if eixo_nome:
                    item["eixo_id"] = eixo_ids.get(eixo_nome, item.get("eixo_id"))
                acao_txt = novo.get("acao") or ""
                if acao_txt:
                    aid = acao_id_by_fold.get(fold(acao_txt))
                    if not aid and acoes_cat:
                        aid = max(acoes_cat, key=lambda a: match_score(acao_txt, a["nome"]))["id"]
                    item["acao_id"] = aid

        # normaliza campo de modo
        modo = item.get("modo_atualizacao") or item.get("modo") or "documental"
        item["modo_atualizacao"] = modo_de(str(modo))
        item["origem_carga"] = origem
        item.pop("modo", None)
        # remove ruído interno se score não foi gravado como sugestão
        if "match_score_sugerido" not in item:
            item.pop("match_score", None)

        inds_out.append(item)
        matriz_rows.append(
            {
                "id": item["id"],
                "codigo_fonte": item["codigo_fonte"],
                "eixo": next((e["nome"] for e in eixos if e["id"] == item.get("eixo_id")), ""),
                "acao": next((a["nome"] for a in acoes_cat if a["id"] == item.get("acao_id")), ""),
                "responsavel": areas_seen.get(item.get("area_id") or "", ""),
                "tipo": item.get("tipo"),
                "modo": item.get("modo_atualizacao"),
                "indicador": item.get("nome"),
                "origem": origem,
                "match_score": score if novo else None,
            }
        )

    # Conteúdos revisados sem pareamento → anexa no diff (não cria 89º indicador)
    pareados_j = {j for _, j, _ in pares}
    orfaos = [pool[j] for j in range(len(pool)) if j not in pareados_j and pool[j].get("origem") == "revisada"]

    catalogo = {
        "fonte": {
            "arquivo": Path(fonte_xlsx).name,
            "abas": ["Ações e indicadores", "Matriz_ARARA (legado para completar 88)"],
            "n_acoes": len(acoes_cat),
            "n_indicadores": len(inds_out),
            "n_indicadores_indice": sum(1 for x in inds_out if x.get("tipo") in {"execucao", "capacidade", "resultado"}),
            "nota": (
                "IDs oficiais IND-001..088 preservados. Conteúdo atualizado pela Matriz Revisada "
                "quando houver correspondência textual; total mantido em 88."
            ),
            "atualizado_em": datetime.now().isoformat(timespec="seconds"),
            "n_alterados": len(alterados),
            "n_orfaos_revisada": len(orfaos),
        },
        "areas": areas,
        "eixos": eixos,
        "metas": metas,
        "acoes": acoes_cat,
        "indicadores": inds_out,
    }
    return catalogo, matriz_rows, alterados, orfaos


def escrever_diff_md(
    acoes: list[dict],
    matriz_rows: list[dict],
    alterados: list[dict],
    orfaos: list[dict],
    path: Path,
) -> None:
    from collections import Counter

    orig = Counter(r.get("origem") for r in matriz_rows)
    linhas = [
        "# Diff — Indicadores Plano El Niño (planilha revisada)",
        "",
        f"**Gerado em:** {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        f"**Fonte nova:** Matriz Plano de Ação_Revisada.xlsx",
        f"**Fonte anterior:** Controle_Indicacoes_El_Nino_SES_MT_2026.xlsx + catálogo IND-001..088",
        "",
        "## Síntese",
        "",
        f"- Ações na planilha revisada: **{len(acoes)}** (antes: 40)",
        f"- Indicadores no sistema: **{len(matriz_rows)}** (contrato: 88 IND-*)",
        f"- Nomes atualizados por match: **{len(alterados)}**",
        f"- Fragmentos revisados sem slot IND (não descartados do texto da ação): **{len(orfaos)}**",
        f"- Origem dos 88: " + " · ".join(f"**{k}**={v}" for k, v in sorted(orig.items())),
        "",
        "## Indicadores com nome alterado",
        "",
        "| ID | Score | Antes → Depois |",
        "| --- | --- | --- |",
    ]
    for a in alterados[:60]:
        linhas.append(
            f"| {a['id']} | {a['score']} | {str(a['antes'])[:55]} → {str(a['depois'])[:55]} |"
        )
    if len(alterados) > 60:
        linhas.append(f"| … | … | +{len(alterados)-60} |")
    linhas.extend(["", "## Ações revisadas (apresentadas agora)", ""])
    for a in acoes:
        frags = "; ".join(a["fragments"][:4])
        linhas.append(f"- **[{a['eixo']}]** {a['acao']}")
        linhas.append(f"  - Resp.: {a['responsavel'] or '—'} · Ind.: {frags or '—'}")
    if orfaos:
        linhas.extend(["", "## Fragmentos revisados sem match forte (já cobertos por outra ação/IND)", ""])
        for o in orfaos[:40]:
            linhas.append(f"- {o.get('indicador')}")
    path.write_text("\n".join(linhas), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx-new", default=str(DEFAULT_NEW))
    ap.add_argument("--xlsx-old", default=str(DEFAULT_OLD))
    ap.add_argument("--catalogo-base", default=str(CATALOGO_BASE if CATALOGO_BASE.exists() else CATALOGO_OUT))
    args = ap.parse_args()
    new_p, old_p = Path(args.xlsx_new), Path(args.xlsx_old)
    base_p = Path(args.catalogo_base)
    if not new_p.exists():
        print("Planilha revisada não encontrada:", new_p)
        return 1
    if not old_p.exists():
        print("Planilha anterior não encontrada:", old_p)
        return 1
    if not base_p.exists():
        print("Catálogo base não encontrado:", base_p)
        return 1

    catalogo_base = yaml.safe_load(base_p.read_text(encoding="utf-8")) or {}
    # se o "base" estiver quebrado (ARARA como id), tenta backup
    first_id = str(((catalogo_base.get("indicadores") or [{}])[0]).get("id") or "")
    if not first_id.startswith("IND-") and CATALOGO_BASE.exists() and base_p != CATALOGO_BASE:
        catalogo_base = yaml.safe_load(CATALOGO_BASE.read_text(encoding="utf-8")) or {}

    acoes = ler_acoes_revisadas(new_p)
    antiga = carregar_arara_antiga(old_p)
    conteudos = expandir_conteudos(acoes, antiga)
    catalogo, matriz_rows, alterados, orfaos = mesclar_mantendo_ind(catalogo_base, acoes, conteudos, str(new_p))
    assert len(catalogo["indicadores"]) == TARGET_N

    CATALOGO_OUT.write_text(
        yaml.safe_dump(catalogo, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )
    MATRIZ_OUT.write_text(
        yaml.safe_dump(
            {"versao": "2026-09-revisada", "n_indicadores": len(matriz_rows), "indicadores": matriz_rows},
            allow_unicode=True,
            sort_keys=False,
            width=120,
        ),
        encoding="utf-8",
    )
    escrever_diff_md(acoes, matriz_rows, alterados, orfaos, DIFF_OUT)

    dest = ROOT / "data" / "input" / new_p.name
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(new_p.read_bytes())
    except Exception as exc:  # noqa: BLE001
        print("aviso: não copiou xlsx para data/input:", exc)

    print(
        f"OK catalogo={CATALOGO_OUT.name} acoes={len(acoes)} inds={TARGET_N} "
        f"alterados={len(alterados)} orfaos_rev={len(orfaos)}"
    )
    print("diff:", DIFF_OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
