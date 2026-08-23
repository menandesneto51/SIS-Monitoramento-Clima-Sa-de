# -*- coding: utf-8 -*-
"""Cadastro, níveis e sessão do painel ARARAS (público vs acesso restrito)."""
from sisclima.auth.access import (
    NIVEIS,
    bootstrap_admin,
    catalogo_municipios,
    catalogo_regionais,
    current_user,
    is_admin,
    is_interno,
    recorte_usuario,
)

__all__ = [
    "NIVEIS",
    "bootstrap_admin",
    "catalogo_municipios",
    "catalogo_regionais",
    "current_user",
    "is_admin",
    "is_interno",
    "recorte_usuario",
]
