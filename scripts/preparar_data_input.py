# -*- coding: utf-8 -*-
"""Cria data/input e copia CSVs de exemplo quando os arquivos oficiais ainda não existem."""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "input"
SIVEP_DROP = INPUT / "sivep_atualizacao"
SAMPLE_DIRS = [
    ROOT / "data" / "sample",
    ROOT / "tmp" / "restore_painel_v9" / "SIS-Monitoramento-Clima-Sa-de-painel-v9" / "data" / "sample",
]

# origem no sample -> destino em data/input (só copia se o destino ainda não existir)
SAMPLE_MAP = {
    "meteorologia.csv": "meteorologia.csv",
    "inmet_alertas.csv": "inmet_alertas.csv",
    "cemaden_alertas.csv": "cemaden_alertas.csv",
    "indicasus_leitos.csv": "indicasus_leitos.csv",
    "lacen_gal.csv": "lacen_gal.csv",
    "sinan_agravos.csv": "sinan_agravos.csv",
    "sim_obitos.csv": "sim_obitos.csv",
    "sentinela_rumores.csv": "sentinela_rumores.csv",
    "sentinela_sg_agregado_semanal.csv": "sentinela_sg_agregado_semanal.csv",
    "sentinela_sg_amostras.csv": "sentinela_sg_amostras.csv",
    "infraestrutura_unidades.csv": "infraestrutura_unidades.csv",
    "estoque_insumos.csv": "estoque_insumos.csv",
    "busca_ativa.csv": "busca_ativa.csv",
    "comunicacao.csv": "comunicacao.csv",
    "qualidade_ar_copernicus.csv": "qualidade_ar_copernicus.csv",
    "municipios_mt.csv": "municipios_mt.csv",
    "municipios_metadata.csv": "municipios_mt.csv",
    "populacao_municipal_mt_2020_2025.csv": "populacao_municipal_mt_2020_2025.csv",
    "populacao_municipios.csv": "populacao_municipal_mt_2020_2025.csv",
}


def _copy_if_missing(src: Path, dest: Path) -> bool:
    if dest.exists() or not src.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return True


def ensure_layout() -> dict:
    INPUT.mkdir(parents=True, exist_ok=True)
    SIVEP_DROP.mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "local" / "sivep").mkdir(parents=True, exist_ok=True)
    copied: list[str] = []

    contatos = INPUT / "contatos_alertas.csv"
    exemplo = ROOT / "config" / "contatos_alertas.exemplo.csv"
    if _copy_if_missing(exemplo, contatos):
        copied.append(contatos.name)

    for sample_dir in SAMPLE_DIRS:
        if not sample_dir.is_dir():
            continue
        for src_name, dest_name in SAMPLE_MAP.items():
            dest = INPUT / dest_name
            if _copy_if_missing(sample_dir / src_name, dest):
                copied.append(dest_name)

    sivep_files = [
        p.name
        for p in SIVEP_DROP.iterdir()
        if p.is_file() and p.suffix.lower() in {".csv", ".xlsx", ".xls", ".parquet", ".dbf"}
        and p.name != ".gitkeep"
    ]
    return {
        "input_dir": str(INPUT),
        "sivep_drop": str(SIVEP_DROP),
        "copied": copied,
        "sivep_exports": sivep_files,
        "sivep_pronto": bool(sivep_files),
    }


def main() -> int:
    info = ensure_layout()
    print(f"[OK] {info['input_dir']}")
    print(f"[OK] {info['sivep_drop']}")
    if info["copied"]:
        print("[INFO] Copiados (só o que faltava): " + ", ".join(info["copied"]))
    else:
        print("[INFO] Nenhum CSV de exemplo copiado (destino já existia ou sample ausente).")
    if info["sivep_pronto"]:
        print("[INFO] SIVEP na pasta de atualização: " + ", ".join(info["sivep_exports"]))
    else:
        print("[AVISO] Sem export SIVEP em data/input/sivep_atualizacao — a aba SRAG fica vazia até o arquivo oficial.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
