# -*- coding: utf-8 -*-
"""
Ciclo operacional com fontes reais.

Uso:
    python -m sisclima.run_real_cycle
    python -m sisclima.run_real_cycle --skip-dw-test
    python -m sisclima.run_real_cycle --export-only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sisclima.core.config import APP_CONFIG, env, as_bool
from sisclima.core.logging_utils import get_logger
from sisclima.ingestion.ibge_municipios import load_or_refresh_municipios
from sisclima.ingestion.sqlserver import build_sqlserver_conn, dw_configured, read_sqlserver, use_sqlserver
from sisclima.ingestion.sivep_local import rebuild_sivep_local_db
from sisclima.pipeline import run_pipeline
from sisclima.validation.validate_sources import validate_sources
from sisclima.validation.reexport_public import fix_resumo, export_public_tables

log = get_logger(__name__)


def prepare_municipios(force: bool = True) -> pd.DataFrame:
    """Baixa/atualiza 142 municípios MT via IBGE com lat/lon."""
    df = load_or_refresh_municipios(force=force)
    if df.empty:
        raise RuntimeError("Falha ao obter municípios do IBGE")

    out_path = APP_CONFIG.input_dir / "municipios_mt.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False, encoding="utf-8-sig")

    # metadata com vulnerabilidade (merge sample se existir)
    meta_sample = APP_CONFIG.input_dir / "municipios_metadata.csv"
    if not meta_sample.exists():
        sample = ROOT / "data" / "sample" / "municipios_metadata.csv"
        if sample.exists():
            meta_sample.write_bytes(sample.read_bytes())

    log.info("Municípios preparados: %s (%d)", out_path, len(df))
    return df


def prepare_populacao() -> Path:
    """Garante arquivo de população no caminho esperado."""
    target = APP_CONFIG.populacao_path
    if target.exists():
        return target

    candidates = [
        APP_CONFIG.input_dir / "populacao_municipal_mt_2020_2025.csv",
        ROOT / "data" / "sample" / "populacao_municipios.csv",
    ]
    for src in candidates:
        if src.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            if src.suffix.lower() in {".xlsx", ".xls"}:
                pd.read_excel(src).to_csv(target, index=False, encoding="utf-8-sig")
            else:
                target.write_bytes(src.read_bytes())
            log.info("População copiada de %s → %s", src, target)
            return target

    raise FileNotFoundError(
        f"População municipal ausente. Coloque o arquivo em {target} "
        "ou defina POPULACAO_CSV no .env"
    )


def test_dw_connection() -> bool:
    if not use_sqlserver():
        if dw_configured():
            log.warning("Credenciais DW incompletas — usando CSV de fallback")
        else:
            log.info("DW não configurado neste ambiente — usando CSV de fallback")
        return False

    conn = build_sqlserver_conn("DW")
    if not conn:
        log.error(
            "DW incompleto. Verifique DW_SERVER, DW_DATABASE, DW_USER e DW_PASSWORD "
            "(ou aliases legados: INDICASUS_SERVER, SQLSERVER_HOST, SENHA_DW, etc.)"
        )
        return False

    try:
        df = read_sqlserver("DW", "SELECT 1 AS ok")
        ok = not df.empty
        if ok:
            log.info("Conexão DW OK")
        return ok
    except Exception as exc:
        log.error("Falha ao conectar DW: %s", exc)
        return False


def update_sivep() -> dict:
    folder = Path(env("SIVEP_UPDATE_FOLDER", "data/input/sivep_atualizacao") or "data/input/sivep_atualizacao")
    if not folder.is_absolute():
        folder = ROOT / folder
    files = list(folder.glob("*"))
    files = [f for f in files if f.is_file() and f.suffix.lower() in {".csv", ".parquet", ".xlsx", ".xls", ".dbf"}]
    if not files:
        log.warning("Pasta SIVEP vazia (%s) — mantendo banco local existente ou CSV fallback", folder)
        return {"status": "skipped", "files": 0}
    result = rebuild_sivep_local_db()
    log.info("SIVEP local atualizado: %s", result)
    return result


def print_validation_report() -> bool:
    df = validate_sources()
    print("\n=== VALIDAÇÃO DE FONTES ===")
    required_fail = []
    for _, row in df.iterrows():
        mark = "OK" if row["ok"] else ("FALHA" if row.get("required") else "aviso")
        print(f"  [{mark}] {row['item']}: {row['detail']}")
        if row.get("required") and not row["ok"]:
            required_fail.append(row["item"])

    if required_fail:
        print(f"\nPendências obrigatórias: {', '.join(required_fail)}")
        return False
    print("\nValidação OK (sem pendências obrigatórias)")
    return True


def export_public_from_db() -> dict:
    from sisclima.core.db import read_table

    resumo = read_table("resumo_municipal_atual")
    if resumo.empty:
        raise RuntimeError("resumo_municipal_atual vazio após pipeline")
    fixed = fix_resumo(resumo)
    return export_public_tables(fixed)


def main():
    parser = argparse.ArgumentParser(description="Ciclo operacional com fontes reais")
    parser.add_argument("--skip-dw-test", action="store_true", help="Não testar conexão DW")
    parser.add_argument("--skip-pipeline", action="store_true", help="Só preparar/validar")
    parser.add_argument("--export-only", action="store_true", help="Só reexportar data/public do SQLite")
    parser.add_argument("--no-alerts", action="store_true", default=True, help="Não enviar alertas")
    args = parser.parse_args()

    env_path = ROOT / ".env"
    if not env_path.exists():
        example = ROOT / ".env.example"
        print(f"AVISO: .env ausente. Copie {example} → .env e preencha credenciais DW/VPN")
        print("Continuando com variáveis de ambiente e defaults...\n")

    if args.export_only:
        counts = export_public_from_db()
        print("Exportado:", counts)
        return

    print("=== PREPARAÇÃO TERRITORIAL ===")
    mun = prepare_municipios(force=True)
    print(f"  {len(mun)} municípios MT com coordenadas")

    pop_path = prepare_populacao()
    print(f"  População: {pop_path}")

    print("\n=== SIVEP LOCAL ===")
    update_sivep()

    if not args.skip_dw_test:
        print("\n=== TESTE DW ===")
        dw_ok = test_dw_connection()
        if use_sqlserver() and not dw_ok:
            print("\nERRO: credenciais DW detectadas, mas conexão falhou.")
            print("Verifique VPN e rode: python3 -m sisclima.validation.diagnose_env")
            sys.exit(1)
        if not use_sqlserver():
            print("  DW não detectado neste ambiente — usando CSVs de data/input como fallback")
            print("  Diagnóstico: python3 -m sisclima.validation.diagnose_env")

    ok = print_validation_report()
    if not ok:
        sys.exit(1)

    if args.skip_pipeline:
        return

    print("\n=== PIPELINE INTEGRADO ===")
    result = run_pipeline(send_alerts=not args.no_alerts)
    print(f"  Status: {result.get('status')}")
    print(f"  Nível estadual: {result.get('nivel')} (score {result.get('score')})")

    print("\n=== EXPORTAÇÃO CLOUD (data/public) ===")
    counts = export_public_from_db()
    for name, n in counts.items():
        print(f"  {name}: {n} linhas")

    print("\nCiclo concluído.")


if __name__ == "__main__":
    main()
