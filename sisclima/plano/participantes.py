# -*- coding: utf-8 -*-
"""Catálogo de pessoas da Sala (Portaria 0590) e cruzamento com e-mails municipais.

Fonte: Controle_Indicacoes_El_Nino_SES_MT_2026.xlsx + destinatários COSEMS.
Não cria senha. Vínculo (perfil + área) só entra em plano_vinculo quando aplicado.
Município SMS não abre a Sala.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from sisclima.core.config import ROOT
from sisclima.plano.acesso import PERFIS_PLANO_IDS, gravar_vinculo, rotulo_perfil_plano
from sisclima.plano.areas import area_id_de_responsavel, rotulo_area

CATALOGO_PATH = ROOT / "config" / "plano_el_nino_participantes.yaml"

SIGLA_AREA = {
    "saf": "assistencia_farmaceutica",
    "covsan": "vigilancia_sanitaria",
    "cpei": "imunizacao",
    "covst": "saude_trabalhador",
    "covsat": "saude_trabalhador",
    "vigiagua": "vigiagua",
    "vigiar": "vigiar",
    "covam": "vigilancia_ambiental",
    "cve": "vigilancia_ambiental",
    "cievs": "cievs",
    "unievs": "cievs",
    "vigidesastre": "cievs",
    "coapre": "atencao_saude",
    "sas": "atencao_saude",
    "cas": "atencao_saude",
    "sgr": "multi_area",
}

EMAILS_SECRETARIA = frozenset(
    {
        "menandesneto@ses.mt.gov.br",
        "tatianabelmonte@ses.mt.gov.br",
    }
)


def _norm_email(email: str) -> str:
    return str(email or "").strip().lower()


def carregar_participantes(path: Path | None = None) -> dict[str, Any]:
    alvo = path or CATALOGO_PATH
    if not alvo.exists():
        return {"participantes": [], "municipios_estrategicos": [], "fonte": ""}
    data = yaml.safe_load(alvo.read_text(encoding="utf-8")) or {}
    data.setdefault("participantes", [])
    data.setdefault("municipios_estrategicos", [])
    return data


def area_id_do_catalogo(*, sigla: str = "", area_texto: str = "", superintendencia: str = "") -> str:
    t = " ".join(x for x in (sigla, area_texto, superintendencia) if x)
    folded = t.casefold().replace("água", "agua")
    if "vigiagua" in folded:
        return "vigiagua"
    if "vigiar" in folded:
        return "vigiar"
    if "vigidesastre" in folded or "cievs" in folded or "unievs" in folded:
        return "cievs"
    if any(k in folded for k in ("arboviro", "dengue", "peconhent", "influenza", "dtha", "renaveh")):
        return "vigilancia_ambiental"
    blob = folded.replace("/", " ")
    for chave, area in SIGLA_AREA.items():
        if chave in blob:
            return area
    return area_id_de_responsavel(t)


def perfil_sugerido(row: dict[str, Any]) -> str:
    email = _norm_email(str(row.get("email") or ""))
    if email in EMAILS_SECRETARIA:
        return "secretaria_executiva_cievs"
    papel = str(row.get("papel") or "").casefold()
    if "titular" in papel and "suplente" not in papel:
        return "coordenador_area"
    area = str(row.get("area_id") or "")
    if area and area not in {"", "multi_area"}:
        return "tecnico_area"
    return "consulta"


def participantes_com_email(cat: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = cat if cat is not None else carregar_participantes()
    out = []
    vistos: set[str] = set()
    for raw in data.get("participantes") or []:
        email = _norm_email(str(raw.get("email") or ""))
        if "@" not in email or email in vistos:
            continue
        vistos.add(email)
        area = str(raw.get("area_id") or "") or area_id_do_catalogo(
            sigla=str(raw.get("sigla") or ""),
            area_texto=str(raw.get("area_texto") or ""),
            superintendencia=str(raw.get("superintendencia") or ""),
        )
        row = dict(raw)
        row["email"] = email
        row["area_id"] = area
        row["area_rotulo"] = rotulo_area(area)
        row["perfil_sugerido"] = str(raw.get("perfil_sugerido") or "") or perfil_sugerido({**row, "area_id": area})
        if row["perfil_sugerido"] not in PERFIS_PLANO_IDS:
            row["perfil_sugerido"] = "consulta"
        row["perfil_rotulo"] = rotulo_perfil_plano(row["perfil_sugerido"])
        row["canal_distribuicao"] = "sala"
        out.append(row)
    return out


def destinatarios_boletim_sala(cat: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """E-mails únicos para o boletim El Niño da Sala (SES + rede ERS + COSEMS).

    Deduplica por e-mail. Não inclui SMS municipais nem pendências sem endereço.
    """
    data = cat if cat is not None else carregar_participantes()
    out: list[dict[str, Any]] = []
    vistos: set[str] = set()

    def _add(raw: dict[str, Any], canal: str) -> None:
        email = _norm_email(str(raw.get("email") or ""))
        if "@" not in email or email in vistos:
            return
        vistos.add(email)
        row = dict(raw)
        row["email"] = email
        row["canal_distribuicao"] = canal
        out.append(row)

    for row in participantes_com_email(data):
        _add(row, "sala")
    for raw in data.get("escritorios_regionais") or []:
        _add(dict(raw), "escritorio_regional")
    for raw in data.get("cosems") or []:
        _add(dict(raw), "cosems")
    return out


def nome_arquivo_boletim_sala(*, se: int | str, ano: int | str = 2026) -> str:
    """Nomenclatura oficial do PDF enviável à Sala.

    Ex.: Boletim Informativo Sala de Situação MT El Niño SE 34-2026.pdf
    """
    se_n = int(str(se).strip())
    ano_n = int(str(ano).strip())
    return f"Boletim Informativo Sala de Situação MT El Niño SE {se_n}-{ano_n}.pdf"


def aplicar_vinculos_catalogo(
    *,
    ator_email: str = "",
    so_institucional: bool = True,
    cat: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Grava plano_vinculo a partir do catálogo. Não cria usuário nem senha."""
    gravados = 0
    pulados = 0
    erros: list[str] = []
    for row in participantes_com_email(cat):
        email = row["email"]
        if so_institucional and not email.endswith(("@ses.mt.gov.br", "@saude.mt.gov.br")):
            pulados += 1
            continue
        ok, msg = gravar_vinculo(
            email=email,
            perfil_plano=str(row.get("perfil_sugerido") or "consulta"),
            area_id=str(row.get("area_id") or ""),
            ator_email=ator_email or "catalogo",
        )
        if ok:
            gravados += 1
        else:
            erros.append(f"{email}: {msg}")
    return {"gravados": gravados, "pulados": pulados, "erros": erros, "n": gravados + pulados + len(erros)}
