# -*- coding: utf-8 -*-
"""Piloto de validação de alertas: SES + Cuiabá + Sorriso (sem fan-out amplo).

Origem do pedido (26/08/2026): incluir cievs@sorriso.mt.gov.br e retomar
canal estadual (e-mail/Telegram). Regionais só entram se houver e-mail real
na planilha piloto (hoje: sem escritórios cadastrados).

Uso:
  python scripts/enviar_alertas_piloto_validacao.py           # só valida + prévia
  python scripts/enviar_alertas_piloto_validacao.py --send    # envia de verdade
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PILOTO_CSV = ROOT / "data" / "input" / "contatos_alertas_piloto_validacao.csv"
OUT_DIR = ROOT / "logs" / "piloto_alertas_validacao"
IBGE_CUIABA = "5103403"
IBGE_SORRISO = "5107925"


def _apply_piloto_env() -> None:
    """Configura escopo restrito do piloto (não altera arquivo .env)."""
    os.environ["ALERT_CONTACTS_CSV"] = str(PILOTO_CSV)
    os.environ["ALERT_FORCE_MUNICIPIOS"] = f"{IBGE_CUIABA},{IBGE_SORRISO}"
    os.environ["ALERT_LAYERS"] = "ses,regionais,municipais,cuiaba"
    os.environ["ALERT_MAX_MUNICIPIOS"] = "0"  # só FORCE (Cuiabá+Sorriso); sem ranking amplo
    os.environ["ALERT_FORCE_ONLY"] = "true"
    # Após aceite CIEVS (2026-09-19): regionais com e-mail institucional ativo no CSV
    os.environ["ALERT_MAX_REGIONAIS"] = "16"
    os.environ["ALERT_REQUIRE_FRESH_ETL"] = os.environ.get("ALERT_REQUIRE_FRESH_ETL", "true")
    os.environ["DATABASE_STRICT_POSTGRES"] = os.environ.get("DATABASE_STRICT_POSTGRES", "true")
    os.environ["ALERT_FANOUT_ENABLED"] = "true"
    os.environ["ALERT_ENVIO_MODO"] = "scheduler_piloto"

def _completeness(payload: dict[str, Any]) -> dict[str, Any]:
    escopo = str(payload.get("escopo") or "")
    checks = {
        "escopo": escopo,
        "alvo": payload.get("alvo_id") or payload.get("municipio") or payload.get("titulo"),
        "nivel": payload.get("nivel") or payload.get("nivel_final"),
        "tem_recomendacoes": bool(payload.get("recomendacoes") or payload.get("orientacoes")),
        "tem_ehf": payload.get("ehf_geocalor") is not None
        or any(
            (i or {}).get("campo") == "ehf_geocalor" and (i or {}).get("valor") is not None
            for i in (payload.get("indicadores") or [])
        ),
        "tem_rit": payload.get("rit_0_100") is not None
        or (payload.get("rit") or {}).get("rit_0_100") is not None,
        "tem_ocupacao_ou_pressao": (
            payload.get("ocupacao_pct") is not None
            or payload.get("ocupacao_leitos_pct") is not None
            or payload.get("sisreg_solicitacoes") is not None
            or payload.get("kpi_sisreg_solicitacoes") is not None
        ),
    }
    # Estadual pode não ter EHF único — exige nível + texto
    if escopo == "estadual":
        checks["ok"] = bool(checks["nivel"]) and bool(
            payload.get("titulo") or payload.get("resumo") or payload.get("corpo")
        )
    else:
        checks["ok"] = bool(checks["nivel"]) and (
            checks["tem_ehf"] or checks["tem_rit"] or checks["tem_ocupacao_ou_pressao"]
        )
    return checks


def main(argv: list[str] | None = None) -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=True)
    _apply_piloto_env()

    ap = argparse.ArgumentParser(description="Piloto alertas SES + Cuiabá + Sorriso")
    ap.add_argument("--send", action="store_true", help="Dispara e-mail/Telegram de verdade")
    ap.add_argument("--force", action="store_true", help="Ignora cooldown/fingerprint")
    args = ap.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not PILOTO_CSV.exists():
        print(f"Planilha piloto ausente: {PILOTO_CSV}", file=sys.stderr)
        return 2

    # 1) Prévia Cuiabá (sempre arquivo; envio opcional)
    from alerta_municipal_cuiaba_v11_10 import (
        build_payload,
        compose_html,
        compose_text,
        avaliar_frescor_cuiaba,
    )

    frescor = avaliar_frescor_cuiaba()
    cuiaba_payload = build_payload()
    cuiaba_txt = compose_text(cuiaba_payload)
    (OUT_DIR / "cuiaba_preview.txt").write_text(cuiaba_txt, encoding="utf-8")
    (OUT_DIR / "cuiaba_preview.html").write_text(compose_html(cuiaba_txt), encoding="utf-8")
    cuiaba_ok = bool(frescor.get("ok")) and cuiaba_payload.get("ehf_geocalor") is not None

    # 2) Pack multinível
    from sisclima.alerts.digest import (
        _central_payloads,
        build_multilevel_pack,
        format_ses_html,
        send_digest,
    )
    from sisclima.alerts.contacts import recipients_for, summarize_contacts

    payloads, fingerprint, meta = build_multilevel_pack()
    central = _central_payloads(payloads)
    mun = [p for p in payloads if p.get("escopo") in {"municipal", "cuiaba"}]
    sorriso = [p for p in mun if "5107925" in str(p.get("alvo_id") or "")]
    cuiaba_pack = [p for p in mun if "5103403" in str(p.get("alvo_id") or "") or p.get("escopo") == "cuiaba"]

    completeness = [_completeness(p) for p in (central[:1] + sorriso[:1] + cuiaba_pack[:1])]
    contacts = summarize_contacts()
    emails_baixada, _ = recipients_for("regional", regional="Baixada Cuiabana")
    emails_sinop, _ = recipients_for("regional", regional="Sinop")
    # Política piloto: Sorriso = CIEVS municipal (não ERS Sinop); Baixada pode ter ERS.
    regionais_status = {
        "Baixada Cuiabana": emails_baixada or [],
        "Sinop": "omitido_no_piloto — alerta Sorriso só cievs@sorriso (não ERS)",
    }

    report: dict[str, Any] = {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "send": bool(args.send),
        "fingerprint": fingerprint,
        "meta_nivel": meta.get("nivel"),
        "n_payloads": len(payloads),
        "n_central": len(central),
        "n_sorriso": len(sorriso),
        "n_cuiaba_pack": len(cuiaba_pack),
        "frescor_cuiaba": frescor,
        "cuiaba_alerta_ok": cuiaba_ok,
        "completeness": completeness,
        "contacts": contacts,
        "recipients_sorriso": recipients_for("municipal", cod_ibge=IBGE_SORRISO, municipio="Sorriso"),
        "recipients_cuiaba": recipients_for("cuiaba", cod_ibge=IBGE_CUIABA),
        "regionais": regionais_status,
        "pedido_origem": "2026-08-26: cievs@sorriso.mt.gov.br + retomar SES/Telegram; manter Cuiabá+Sorriso",
    }

    if central:
        (OUT_DIR / "ses_preview.html").write_text(format_ses_html(central[0]), encoding="utf-8")

    # 3) Envio
    send_result: dict[str, Any] = {"status": "nao_solicitado"}
    cuiaba_send: dict[str, Any] = {"status": "nao_solicitado"}

    if args.send:
        if not cuiaba_ok:
            print("BLOQUEIO: Cuiabá sem frescor/EHF — não envia.", file=sys.stderr)
            report["send_result"] = {"status": "bloqueado_cuiaba_incompleto"}
            (OUT_DIR / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
            )
            return 1
        if not any(c.get("ok") for c in completeness):
            print("BLOQUEIO: payloads incompletos.", file=sys.stderr)
            report["send_result"] = {"status": "bloqueado_incompleto"}
            (OUT_DIR / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
            )
            return 1

        os.environ["SEND_ALERT_ON_LEVEL_CHANGE"] = "true"
        send_result = send_digest(force=True if args.force else True, skip_cooldown=True)

        # Alerta municipal Cuiabá (script dedicado)
        import subprocess

        cmd = [
            sys.executable,
            str(ROOT / "alerta_municipal_cuiaba_v11_10.py"),
            "--send",
            "--force",
        ]
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
        cuiaba_send = {
            "status": "ok" if proc.returncode == 0 else "erro",
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-800:],
            "stderr_tail": (proc.stderr or "")[-400:],
        }

    report["send_result"] = send_result
    report["cuiaba_send"] = cuiaba_send
    (OUT_DIR / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    print("PILOTO ALERTAS — SES + Cuiabá + Sorriso")
    print(f"  nivel={meta.get('nivel')} payloads={len(payloads)} central={len(central)}")
    print(f"  sorriso_payloads={len(sorriso)} emails={report['recipients_sorriso'][0]}")
    print(f"  cuiaba_emails={report['recipients_cuiaba'][0]} frescor_ok={cuiaba_ok}")
    print(f"  regionais: Baixada={emails_baixada or '—'}; Sinop=omitido (CIEVS municipal)")
    print(f"  send={args.send} digest={send_result.get('status')} cuiaba_script={cuiaba_send.get('status')}")
    print(f"  out={OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
