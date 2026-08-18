# -*- coding: utf-8 -*-
"""Valida a ingestão VigiBarragens (SIGBM/ANM) e o agregado municipal de exposição."""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(".env"), override=True)

import pandas as pd

from sisclima.core.config import env
from sisclima.core.db import init_db, read_table, write_df
from sisclima.ingestion.vigibarragens import (
    barragens_alerta_for_municipio,
    load_vigibarragens_bundle,
)


def main() -> int:
    print("USE_VIGIBARRAGENS=", env("USE_VIGIBARRAGENS", "true"))
    print("VIGIBARRAGENS_URL=", env("VIGIBARRAGENS_URL") or "(vazio → usa CSV/amostra)")
    init_db()

    bundle = load_vigibarragens_bundle()
    for table_name, frame in bundle.items():
        write_df(frame if frame is not None else pd.DataFrame(), table_name)
        print(table_name, 0 if frame is None else len(frame))

    barragens = read_table("vigibarragens_barragens")
    risco = read_table("vigibarragens_exposicao_municipal")
    assert not barragens.empty, "Cadastro de barragens vazio (verifique CSV/amostra)."
    assert not risco.empty, "Agregado municipal VigiBarragens vazio."

    pop_zas = pd.to_numeric(risco["populacao_zas_total"], errors="coerce").fillna(0).sum()
    print(f"barragens={len(barragens)} municipios={len(risco)} pop_zas={int(pop_zas)}")
    print("distribuicao nivel_sis:", risco["nivel_sis"].value_counts().to_dict())

    # Exemplo de elevação de nível para o município mais exposto.
    top = risco.sort_values("populacao_zas_total", ascending=False).iloc[0]
    motivo, nivel = barragens_alerta_for_municipio(
        risco, municipio=top.get("municipio"), cod_ibge=top.get("cod_ibge")
    )
    print(f"top={top.get('municipio')} nivel={nivel} motivo={motivo}")

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
