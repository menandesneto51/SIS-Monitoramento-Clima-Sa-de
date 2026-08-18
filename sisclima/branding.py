"""Identidade institucional compartilhada pelo painel e pelos alertas ARARAS MT."""
from __future__ import annotations

import html
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRAND_ASSETS = ROOT / "assets" / "branding"

SYSTEM_NAME = "ARARAS MT"
SYSTEM_EXPANSION = "Análise, Resposta e Acompanhamento de Riscos, Agravos e Saúde"
SYSTEM_TAGLINE = "Clima, ambiente e saúde em uma só visão."
SYSTEM_OWNER = "Secretaria de Estado de Saúde de Mato Grosso · CIEVS-MT"
PROJECT_DESCRIPTION = (
    f"{SYSTEM_NAME} ({SYSTEM_EXPANSION}) é a plataforma oficial de inteligência e apoio à gestão da SES-MT "
    "para integrar clima, ambiente e saúde. Complementa os sistemas do SUS e não substitui protocolos, "
    "notificação nem decisão da autoridade."
)

ARARAS_LOGO_PATH = BRAND_ASSETS / "araras-mt-logo-horizontal.png"
ARARAS_SYMBOL_PATH = BRAND_ASSETS / "araras-mt-simbolo.png"
ALERT_BRAND_CARD_PATH = BRAND_ASSETS / "araras-mt-cartao-institucional.png"
GOV_SES_LOGO_PATH = BRAND_ASSETS / "governo-ses-mt-fundo-institucional.png"
CIEVS_MT_LOGO_PATH = BRAND_ASSETS / "cievs-mt.png"
REDE_CIEVS_LOGO_PATH = BRAND_ASSETS / "rede-cievs.png"
VIGIDESASTRES_LOGO_PATH = BRAND_ASSETS / "vigidesastres.png"


def branded_subject(subject: str) -> str:
    """Padroniza o assunto sem duplicar a marca quando o chamador já a incluiu."""
    cleaned = str(subject or "").strip()
    if cleaned.upper().startswith("[ARARAS MT]"):
        return cleaned
    return f"[ARARAS MT] {cleaned}" if cleaned else "[ARARAS MT] Alerta operacional"


def plain_header() -> str:
    return (
        f"{SYSTEM_NAME} · {SYSTEM_TAGLINE}\n"
        f"{SYSTEM_EXPANSION}\n"
        f"{PROJECT_DESCRIPTION}\n"
        f"{SYSTEM_OWNER} · Rede CIEVS · Vigidesastres"
    )


def plain_footer() -> str:
    return (
        f"{SYSTEM_NAME} · CIEVS-MT / SES-MT · Rede CIEVS · Vigidesastres\n"
        "Ferramenta de apoio à gestão. Validar no painel e no território antes da comunicação oficial."
    )


def wrap_plain_message(body: str) -> str:
    text = str(body or "").strip()
    if PROJECT_DESCRIPTION in text:
        return text
    return f"{plain_header()}\n\n{text}\n\n{plain_footer()}".strip()


def html_email_shell(body_html: str) -> str:
    """Envolve o conteúdo integral do alerta com uma única assinatura institucional."""
    content = str(body_html or "").strip()
    return f"""
    <div style="margin:0;padding:20px;background:#eef5f5;font-family:Segoe UI,Arial,sans-serif;color:#12354e">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
             style="max-width:920px;margin:0 auto;background:#ffffff;border-collapse:collapse;border:1px solid #d7e2e5">
        <tr>
          <td style="padding:16px 20px;text-align:center;border-bottom:4px solid #087f82">
            <img src="cid:institucional-card"
                 alt="ARARAS MT · SES-MT · Governo de Mato Grosso · CIEVS-MT · Rede CIEVS · Vigidesastres"
                 style="display:block;max-width:800px;width:100%;height:auto;margin:0 auto" />
          </td>
        </tr>
        <tr><td style="padding:20px">{content}</td></tr>
        <tr>
          <td style="padding:13px 20px;background:#073f67;color:#ffffff;font-size:12px;line-height:1.45">
            <strong>{html.escape(SYSTEM_NAME)}</strong> · CIEVS-MT / SES-MT · Rede CIEVS · Vigidesastres<br />
            Ferramenta de apoio à gestão. Validar no painel e no território antes da comunicação oficial.
          </td>
        </tr>
      </table>
    </div>
    """


INLINE_BRAND_ASSETS = {
    "institucional-card": ALERT_BRAND_CARD_PATH,
}
