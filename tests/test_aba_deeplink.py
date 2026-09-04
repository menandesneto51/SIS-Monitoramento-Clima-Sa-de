# -*- coding: utf-8 -*-
"""Deep-links ?aba= / ?modulo= do site institucional → abas do painel."""
from __future__ import annotations


def _resolve_aba_query(raw: str, valid: set[str]) -> str | None:
    """Cópia espelhada da resolução usada em app_v9 (sem importar Streamlit)."""
    text = str(raw or "").strip()
    if not text:
        return None
    if text in valid:
        return text
    slug = (
        text.lower()
        .replace("ã", "a")
        .replace("á", "a")
        .replace("â", "a")
        .replace("é", "e")
        .replace("ê", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ô", "o")
        .replace("ú", "u")
        .replace("ç", "c")
        .replace("ñ", "n")
        .replace("_", "-")
        .replace(" / ", "-")
        .replace("/", "-")
        .replace(" ", "-")
    )
    while "--" in slug:
        slug = slug.replace("--", "-")
    aliases = {
        "ce": "El Niño / Contingência",
        "qualidade-ar": "Qualidade do ar",
        "ar": "Qualidade do ar",
        "as": "Arboviroses",
        "rt": "Mapas",
        "assistencia": "Assistência",
        "sala": "Sala de Situação / Plano El Niño",
        "visao": "Visão executiva",
    }
    alias = aliases.get(slug)
    if alias and alias in valid:
        return alias
    for key in valid:
        key_slug = (
            key.lower()
            .replace("ã", "a")
            .replace("á", "a")
            .replace("â", "a")
            .replace("é", "e")
            .replace("ê", "e")
            .replace("í", "i")
            .replace("ó", "o")
            .replace("ô", "o")
            .replace("ú", "u")
            .replace("ç", "c")
            .replace("ñ", "n")
            .replace(" / ", "-")
            .replace("/", "-")
            .replace(" ", "-")
        )
        if key_slug == slug:
            return key
    return None


def test_resolve_exact_key():
    valid = {"Qualidade do ar", "Mapas"}
    assert _resolve_aba_query("Qualidade do ar", valid) == "Qualidade do ar"


def test_resolve_slug_alias():
    valid = {"Qualidade do ar", "Arboviroses", "Mapas", "El Niño / Contingência"}
    assert _resolve_aba_query("ar", valid) == "Qualidade do ar"
    assert _resolve_aba_query("ce", valid) == "El Niño / Contingência"
    assert _resolve_aba_query("qualidade-ar", valid) == "Qualidade do ar"


def test_resolve_ignores_unavailable_tab():
    valid = {"Mapas", "Visão executiva"}
    assert _resolve_aba_query("assistencia", valid) is None
