# -*- coding: utf-8 -*-
"""Compat: reexporta o motor de correlação."""
from sisclima.engines.correlation_stats import DESFECHOS, EXPOSICOES, compute_spearman_pairs

__all__ = ["EXPOSICOES", "DESFECHOS", "compute_spearman_pairs"]
