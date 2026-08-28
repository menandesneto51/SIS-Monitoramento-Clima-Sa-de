# -*- coding: utf-8 -*-
"""Áreas canônicas do Plano — isolamento de escrita."""
from __future__ import annotations

import re
import unicodedata

AREAS_CANONICAS: tuple[tuple[str, str], ...] = (
    ("assistencia_farmaceutica", "Assistência Farmacêutica"),
    ("vigilancia_sanitaria", "Vigilância Sanitária"),
    ("imunizacao", "Imunização e Rede de Frio"),
    ("saude_trabalhador", "Saúde do Trabalhador"),
    ("vigiagua", "Vigiágua"),
    ("vigiar", "Vigiar"),
    ("vigilancia_ambiental", "Vigilância ambiental e epidemiológica"),
    ("atencao_saude", "Atenção à Saúde / Regulação"),
    ("comunicacao", "Comunicação de risco"),
    ("logistica", "Logística"),
    ("cievs", "CIEVS / Vigidesastres"),
    ("multi_area", "Articulação multiárea (secretaria-executiva)"),
)


def _fold(texto: str) -> str:
    txt = unicodedata.normalize("NFKD", str(texto or ""))
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", txt).strip().casefold()


def area_id_de_responsavel(responsavel: str) -> str:
    """Mapeia o texto da planilha para a área que pode editar o registro."""
    t = _fold(responsavel)
    if not t:
        return "multi_area"
    regras: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("assistencia_farmaceutica", ("assistencia farmaceutica", "assistência farmacêutica")),
        ("vigilancia_sanitaria", ("covsan", "vigilancia sanitaria", "vigilância sanitária")),
        ("imunizacao", ("cpei", "imunizacao", "imunização", "rede de frio")),
        ("saude_trabalhador", ("covsat", "cerest", "trabalhador")),
        ("vigiagua", ("vigiagua", "vigiágua", "lacen")),
        ("vigiar", ("vigiar",)),
        ("comunicacao", ("comunicacao", "comunicação")),
        ("logistica", ("logistica", "logística")),
        ("atencao_saude", ("atencao", "atenção", "regulacao", "regulação", "urgencia", "urgência")),
        ("vigilancia_ambiental", ("covsam", "vigilancia ambiental", "epidemiolog")),
        ("cievs", ("cievs", "vigidesastres")),
    )
    for area_id, chaves in regras:
        if any(ch in t for ch in chaves):
            return area_id
    return "multi_area"


def rotulo_area(area_id: str) -> str:
    for key, lbl in AREAS_CANONICAS:
        if key == area_id:
            return lbl
    return area_id or "—"
