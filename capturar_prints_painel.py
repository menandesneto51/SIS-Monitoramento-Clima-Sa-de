# -*- coding: utf-8 -*-
"""Captura prints úteis (conteúdo) das abas Mapas / Assistência / Alertas."""
from __future__ import annotations

import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / "docs" / "apresentacoes" / "prints_painel"
URL = "http://localhost:8501"

JOBS = [
    {
        "aba": "Mapas",
        "file": "03_mapas_conteudo.png",
        "seek": ["Mapas municipais", "Nível operacional", "choropleth", "Mapa"],
    },
    {
        "aba": "Assistência",
        "file": "04_assistencia_conteudo.png",
        "seek": ["índice de pressão", "Índice de pressão", "IndicaSUS", "SISREG", "semáforo"],
    },
    {
        "aba": "Alertas",
        "file": "05_alertas_conteudo.png",
        "seek": ["Alertas multinível", "① Estadual", "Estadual (SES)", "Vigidesastre", "multinível"],
    },
    {
        "aba": "Visão executiva",
        "file": "02_visao_conteudo.png",
        "seek": ["Visão executiva", "Nível operacional estadual", "ROXA", "Situação geral"],
    },
]


def click_aba(page, nome: str) -> bool:
    # Streamlit: botões/radios com o texto da aba
    for sel in (
        page.get_by_role("radio", name=nome, exact=True),
        page.locator("label").filter(has_text=nome),
        page.get_by_text(nome, exact=True),
    ):
        try:
            if sel.count() > 0:
                sel.first.click(timeout=8000, force=True)
                return True
        except Exception:
            continue
    return False


def scroll_to_content(page, keywords: list[str]) -> None:
    # rola o main container do Streamlit
    page.evaluate(
        """
        () => {
          const main = document.querySelector('[data-testid="stAppViewContainer"]')
            || document.querySelector('section.main')
            || document.body;
          main.scrollTo(0, 0);
        }
        """
    )
    page.wait_for_timeout(800)
    for kw in keywords:
        loc = page.get_by_text(kw, exact=False)
        try:
            if loc.count() > 0:
                loc.first.scroll_into_view_if_needed(timeout=5000)
                page.wait_for_timeout(1200)
                return
        except Exception:
            continue
    # fallback: desce bastante
    for _ in range(6):
        page.mouse.wheel(0, 900)
        page.wait_for_timeout(400)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.goto(URL, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(9000)

        for job in JOBS:
            ok = click_aba(page, job["aba"])
            page.wait_for_timeout(5000)
            scroll_to_content(page, job["seek"])
            page.wait_for_timeout(2500)
            path = OUT / job["file"]
            page.screenshot(path=str(path), full_page=False)
            print(f"[{'OK' if ok else 'WARN'}] {job['aba']} -> {path.name} ({path.stat().st_size} bytes)")

        browser.close()

    # cópia para Downloads (arrastar fácil no Canva)
    dest = Path.home() / "Downloads" / "SIS_prints_painel"
    dest.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.png"):
        (dest / f.name).write_bytes(f.read_bytes())
    print(f"[OK] cópia Downloads: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
