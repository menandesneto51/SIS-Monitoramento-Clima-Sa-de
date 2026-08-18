# -*- coding: utf-8 -*-
"""Cadastro, níveis e sessão do painel ARARAS (público vs acesso restrito)."""
from sisclima.auth.access import (
    NIVEIS,
    bootstrap_admin,
    current_user,
    is_admin,
    is_interno,
)

__all__ = [
    "NIVEIS",
    "bootstrap_admin",
    "current_user",
    "is_admin",
    "is_interno",
]
