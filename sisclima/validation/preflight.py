from __future__ import annotations

from pathlib import Path
import socket
from typing import Any

import pandas as pd

from sisclima.core.config import APP_CONFIG, env, as_bool, ROOT
from sisclima.ingestion.sqlserver import probe_sqlserver
from sisclima.validation.validate_sources import looks_like_placeholder, validate_sources


def _bool_feature_enabled(name: str, default: bool = False) -> bool:
    return as_bool(env(name, "true" if default else "false"), default)


def _socket_check(host: str | None, port: str | int | None, timeout: float = 3.0) -> tuple[bool, str]:
    if not host or not port:
        return False, "host/porta ausentes"
    try:
        p = int(port)
    except Exception:
        return False, f"porta inválida: {port}"
    try:
        with socket.create_connection((str(host), p), timeout=timeout):
            return True, "conectividade TCP OK"
    except Exception as exc:
        return False, f"falha TCP: {exc}"


def _check_dw_runtime() -> dict[str, Any]:
    enabled = _bool_feature_enabled("USE_SQLSERVER", False)
    if not enabled:
        return {
            "item": "DW runtime query",
            "ok": True,
            "required": False,
            "severity": "info",
            "detail": "USE_SQLSERVER=false",
        }

    if looks_like_placeholder(env("DW_PASSWORD")):
        return {
            "item": "DW runtime query",
            "ok": False,
            "required": True,
            "severity": "critical",
            "detail": "DW_PASSWORD ainda é placeholder (ex.: COLE_AQUI_A_SENHA_DW). Coloque a senha real no .env e salve o arquivo.",
        }

    host = env("DW_SERVER") or env("DW_HOST")
    port = env("DW_PORT", "1433")
    tcp_ok, tcp_detail = _socket_check(host, port)
    if not tcp_ok:
        return {
            "item": "DW runtime query",
            "ok": False,
            "required": True,
            "severity": "critical",
            "detail": f"{tcp_detail} ({host}:{port})",
        }

    probe = probe_sqlserver("DW")
    return {
        "item": "DW runtime query",
        "ok": bool(probe.get("ok")),
        "required": True,
        "severity": "critical" if not probe.get("ok") else "info",
        "detail": str(probe.get("detail") or ""),
    }


def _check_copernicus_credential() -> dict[str, Any]:
    enabled = _bool_feature_enabled("USE_COPERNICUS", False)
    if not enabled:
        return {
            "item": "Copernicus credencial",
            "ok": True,
            "required": False,
            "severity": "info",
            "detail": "USE_COPERNICUS=false",
        }

    key = env("COPERNICUS_KEY")
    has_dotfile = (ROOT / ".cdsapirc").exists() or (Path.home() / ".cdsapirc").exists()
    if looks_like_placeholder(key) and not has_dotfile:
        return {
            "item": "Copernicus credencial",
            "ok": False,
            "required": True,
            "severity": "critical",
            "detail": "COPERNICUS_KEY ainda está com placeholder e .cdsapirc não foi encontrado",
        }

    ok = (not looks_like_placeholder(key)) or has_dotfile
    detail = (
        "COPERNICUS_KEY presente"
        if not looks_like_placeholder(key)
        else (".cdsapirc presente" if has_dotfile else "COPERNICUS_KEY/.cdsapirc ausentes")
    )
    return {
        "item": "Copernicus credencial",
        "ok": ok,
        "required": True,
        "severity": "critical" if not ok else "info",
        "detail": detail,
    }


def _check_inmet_url() -> dict[str, Any]:
    enabled = _bool_feature_enabled("USE_INMET", False)
    if not enabled:
        return {
            "item": "INMET endpoint",
            "ok": True,
            "required": False,
            "severity": "info",
            "detail": "USE_INMET=false",
        }
    url = env("INMET_ALERTS_URL")
    if looks_like_placeholder(url):
        return {
            "item": "INMET endpoint",
            "ok": False,
            "required": True,
            "severity": "warning",
            "detail": "INMET_ALERTS_URL ainda está com placeholder; pipeline usará CSV local",
        }
    ok = bool(url)
    return {
        "item": "INMET endpoint",
        "ok": ok,
        "required": True,
        "severity": "warning" if not ok else "info",
        "detail": url if ok else "INMET_ALERTS_URL ausente (ficará no fallback CSV)",
    }


def _check_core_files() -> list[dict[str, Any]]:
    # Mantido apenas no run_preflight via validate_sources + checagens runtime.
    # Esta função cobre os caminhos canônicos usados pelo app.
    checks: list[dict[str, Any]] = []
    required_paths = [
        ("Shapefile municipal", APP_CONFIG.shapefile_municipios),
        ("CSV municípios", APP_CONFIG.municipios_csv),
        ("População municipal", APP_CONFIG.populacao_path),
    ]
    for label, path in required_paths:
        p = Path(path)
        ok = p.exists()
        checks.append({
            "item": label,
            "ok": ok,
            "required": True,
            "severity": "critical" if not ok else "info",
            "detail": str(p) if ok else f"ausente: {p}",
        })

    sivep_enabled = _bool_feature_enabled("USE_SIVEP_LOCAL", True)
    sivep_folder = APP_CONFIG.root / (
        env("SIVEP_UPDATE_FOLDER", "data/input/sivep_atualizacao") or "data/input/sivep_atualizacao"
    )
    folder_exists = sivep_folder.exists()
    files_count = 0
    if folder_exists:
        files_count = len([p for p in sivep_folder.iterdir() if p.is_file()])
    checks.append({
        "item": "SIVEP pasta atualização",
        "ok": folder_exists,
        "required": sivep_enabled,
        "severity": "critical" if sivep_enabled and not folder_exists else "info",
        "detail": f"{sivep_folder} | arquivos={files_count}" if folder_exists else f"ausente: {sivep_folder}",
    })
    return checks


def _canonical_item_name(item: str) -> str:
    """Normaliza nomes equivalentes para consolidar o relatório operacional."""
    key = str(item or "").strip().lower()
    aliases = {
        "shapefile municipal mt": "Shapefile municipal",
        "shapefile municipal": "Shapefile municipal",
        "csv municípios mt": "CSV municípios",
        "csv municipios mt": "CSV municípios",
        "csv municípios": "CSV municípios",
        "csv municipios": "CSV municípios",
        "população municipal": "População municipal",
        "populacao municipal": "População municipal",
        "copernicus cds/ads credencial": "Copernicus credencial",
        "copernicus credencial": "Copernicus credencial",
        "pasta atualização sivep": "SIVEP pasta atualização",
        "pasta atualizacao sivep": "SIVEP pasta atualização",
        "sivep pasta atualização": "SIVEP pasta atualização",
        "sivep pasta atualizacao": "SIVEP pasta atualização",
    }
    return aliases.get(key, str(item))


def run_preflight() -> pd.DataFrame:
    """Executa pré-flight operacional para ambiente de produção.

    Combina validações estáticas (validate_sources) com checagens de conectividade
    e disponibilidade de runtime para reduzir falhas durante o ciclo real.
    """
    base = validate_sources().copy()
    base["severity"] = base.apply(
        lambda r: "critical" if bool(r.get("required")) and not bool(r.get("ok")) else "info",
        axis=1,
    )

    runtime_rows = [
        _check_dw_runtime(),
        _check_copernicus_credential(),
        _check_inmet_url(),
        *_check_core_files(),
    ]
    runtime_df = pd.DataFrame(runtime_rows)

    out = pd.concat([base, runtime_df], ignore_index=True, sort=False)
    out["required"] = out["required"].fillna(False).astype(bool)
    out["ok"] = out["ok"].fillna(False).astype(bool)
    out["severity"] = out["severity"].fillna("info")
    out["detail"] = out["detail"].fillna("").astype(str)
    out["item"] = out["item"].map(_canonical_item_name)

    # Evita duplicidade de item no relatório final (usa o pior status encontrado).
    sev_rank = {"info": 0, "warning": 1, "critical": 2}
    out["_sev_rank"] = out["severity"].astype(str).str.lower().map(sev_rank).fillna(0)
    out["_ok_rank"] = out["ok"].astype(int)  # 0 pior que 1
    out = out.sort_values(["item", "_ok_rank", "_sev_rank"], ascending=[True, True, False])
    out = out.drop_duplicates(subset=["item"], keep="first")
    out = out.drop(columns=["_sev_rank", "_ok_rank"])
    return out[["item", "ok", "required", "severity", "detail"]].reset_index(drop=True)


def summarize_preflight(df: pd.DataFrame) -> dict[str, int]:
    return {
        "total": int(len(df)),
        "ok": int(df["ok"].sum()),
        "fail": int((~df["ok"]).sum()),
        "critical_fail": int(((~df["ok"]) & df["severity"].astype(str).str.lower().eq("critical")).sum()),
        "required_fail": int(((~df["ok"]) & df["required"]).sum()),
    }
