# -*- coding: utf-8 -*-
"""Prévia de alertas para homologação — SEM envio SMTP/Telegram.

Uso:
  python scripts/homologar_alertas_preview.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["SEND_ALERT_ON_LEVEL_CHANGE"] = "false"
os.environ["ALERT_FANOUT_ENABLED"] = "false"
os.environ["ALERT_FANOUT_SIMULATE"] = "true"

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)
# Reforça após dotenv
os.environ["SEND_ALERT_ON_LEVEL_CHANGE"] = "false"
os.environ["ALERT_FANOUT_ENABLED"] = "false"


def main() -> int:
    out_dir = ROOT / "logs" / "homologacao_alertas"
    out_dir.mkdir(parents=True, exist_ok=True)

    from sisclima.alerts.digest import (
        _central_payloads,
        build_multilevel_pack,
        format_payload_html,
        format_ses_html,
    )
    from sisclima.core.config import env

    payloads, fingerprint, meta = build_multilevel_pack()
    central = _central_payloads(payloads)

    report = {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "envio_real": False,
        "SEND_ALERT_ON_LEVEL_CHANGE": env("SEND_ALERT_ON_LEVEL_CHANGE", "false"),
        "ALERT_FANOUT_ENABLED": env("ALERT_FANOUT_ENABLED", "false"),
        "fingerprint": fingerprint,
        "meta": {k: meta.get(k) for k in ("nivel", "n_gerados", "n_municipios") if k in meta or True},
        "n_payloads": len(payloads),
        "n_central": len(central),
        "ALERT_EMAIL_TO_configured": bool(env("ALERT_EMAIL_TO")),
    }
    # meta may use different keys
    report["meta"] = {
        "nivel": meta.get("nivel"),
        "n_gerados": meta.get("n_gerados", len(payloads)),
        "keys": list(meta.keys())[:20],
    }

    (out_dir / "digest_meta.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    if central:
        p0 = central[0]
        html = format_ses_html(p0) if callable(format_ses_html) else format_payload_html(p0)
        (out_dir / "digest_estadual_preview.html").write_text(html, encoding="utf-8")
        # texto resumido
        lines = [
            f"Nível meta: {meta.get('nivel')}",
            f"Fingerprint: {fingerprint}",
            f"Payloads gerados: {len(payloads)} · centrais: {len(central)}",
            f"Município amostra: {p0.get('municipio') or p0.get('escopo') or p0.get('titulo')}",
            f"EHF: {p0.get('ehf_geocalor') or (p0.get('indicadores') and 'ver indicadores')}",
            f"RIT: {p0.get('rit_0_100')} / {p0.get('rit_faixa')}",
        ]
        (out_dir / "digest_estadual_preview.txt").write_text("\n".join(lines), encoding="utf-8")

    # Cuiabá
    from alerta_municipal_cuiaba_v11_10 import build_payload, compose_html, compose_text

    payload = build_payload()
    text = compose_text(payload)
    (out_dir / "alerta_cuiaba_preview.txt").write_text(text, encoding="utf-8")
    (out_dir / "alerta_cuiaba_preview.html").write_text(compose_html(text), encoding="utf-8")
    cuiaba_check = {
        "ehf_geocalor": payload.get("ehf_geocalor"),
        "data_ehf_geocalor": payload.get("data_ehf_geocalor"),
        "rit_0_100": payload.get("rit_0_100"),
        "rit_faixa": payload.get("rit_faixa"),
        "nivel_final": payload.get("nivel_final"),
        "ehf_ok": payload.get("ehf_geocalor") is not None,
        "rit_ok": payload.get("rit_0_100") is not None,
    }
    (out_dir / "alerta_cuiaba_checks.json").write_text(
        json.dumps(cuiaba_check, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    # Contatos modelo
    contatos_dst = ROOT / "data" / "input" / "contatos_alertas.csv"
    contatos_ex = ROOT / "config" / "contatos_alertas.exemplo.csv"
    contatos_note = "ja_existe"
    if not contatos_dst.exists() and contatos_ex.exists():
        contatos_dst.parent.mkdir(parents=True, exist_ok=True)
        contatos_dst.write_bytes(contatos_ex.read_bytes())
        contatos_note = "copiado_do_exemplo_fanout_permanece_off"

    report["cuiaba"] = cuiaba_check
    report["contatos_alertas"] = contatos_note if contatos_dst.exists() else "ausente"
    (out_dir / "resumo_homologacao_alertas.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    print("ALERTAS PREVIEW — sem envio")
    print(f"  nivel={meta.get('nivel')} payloads={len(payloads)} central={len(central)}")
    print(f"  cuiaba ehf_ok={cuiaba_check['ehf_ok']} rit_ok={cuiaba_check['rit_ok']} nivel={cuiaba_check['nivel_final']}")
    print(f"  out={out_dir}")
    ok = bool(cuiaba_check["ehf_ok"] and cuiaba_check["rit_ok"] and payloads)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
