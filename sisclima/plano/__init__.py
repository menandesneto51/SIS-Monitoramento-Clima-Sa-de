# -*- coding: utf-8 -*-
"""Plano de Ação El Niño — acompanhamento operacional no ARARAS MT.

Camada estrutural: catálogo, máquina de status, isolamento por área,
histórico append-only e Sala de Situação restrita. Não altera o boletim semanal.
"""
from __future__ import annotations

from sisclima.plano.acesso import PERFIS_PLANO, pode_abrir_sala, pode_editar_area, pode_validar
from sisclima.plano.catalogo import carregar_catalogo
from sisclima.plano.indicadores import cumprimento_indice, progresso, quadro_indicadores, registrar_leitura
from sisclima.plano.operacao import percentual_implementacao, percentual_oficial, resumo_sala, status_cor

__all__ = [
    "PERFIS_PLANO",
    "carregar_catalogo",
    "percentual_implementacao",
    "percentual_oficial",
    "pode_abrir_sala",
    "pode_editar_area",
    "pode_validar",
    "resumo_sala",
    "status_cor",
    "progresso",
    "quadro_indicadores",
    "registrar_leitura",
    "cumprimento_indice",
]
