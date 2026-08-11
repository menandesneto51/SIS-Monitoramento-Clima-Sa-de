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

ARARAS_LOGO_PATH = BRAND_ASSETS / "araras-mt-logo-horizontal.png"
ARARAS_SYMBOL_PATH = BRAND_ASSETS / "araras-mt-simbolo.png"
ALERT_BRAND_CARD_PATH = BRAND_ASSETS / "araras-mt-cartao-institucional.png"
GOV_SES_LOGO_PATH = BRAND_ASSETS / "governo-ses-mt-fundo-institucional.png"
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
        f"{SYSTEM_OWNER} · Rede CIEVS · Vigidesastres"
    )


def plain_footer() -> str:
    return (
        f"{SYSTEM_NAME} · CIEVS-MT / SES-MT · Rede CIEVS · Vigidesastres\n"
        "Ferramenta de apoio à gestão. Validar no painel e no território antes da comunicação oficial."
    )


def wrap_plain_message(body: str) -> str:
    text = str(body or "").strip()
    if text.startswith(SYSTEM_NAME):
        return text
    return f"{plain_header()}\n\n{text}\n\n{plain_footer()}".strip()


def html_email_shell(body_html: str) -> str:
    """Envolve qualquer boletim HTML com o cabeçalho institucional e CIDs das marcas."""
    content = str(body_html or "").strip()
    return f"""
    <div style="margin:0;padding:20px;background:#eef5f5;font-family:Segoe UI,Arial,sans-serif;color:#12354e">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
             style="max-width:920px;margin:0 auto;background:#ffffff;border-collapse:collapse;border:1px solid #d7e2e5">
        <tr>
          <td style="padding:16px 20px;border-bottom:4px solid #087f82">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse">
              <tr>
                <td style="width:52%;vertical-align:middle;padding-right:14px">
                  <img src="cid:araras-logo" alt="ARARAS MT — {html.escape(SYSTEM_TAGLINE)}"
                       style="display:block;max-width:430px;width:100%;height:auto" />
                </td>
                <td style="vertical-align:middle;text-align:right">
                  <img src="cid:governo-ses-logo" alt="SES-MT e Governo de Mato Grosso"
                       style="display:inline-block;max-width:235px;width:100%;height:auto;margin-bottom:8px" /><br />
                  <span style="display:inline-block;color:#073f67;font-size:13px;font-weight:800;margin-right:10px">CIEVS-MT</span>
                  <img src="cid:rede-cievs-logo" alt="Rede CIEVS"
                       style="display:inline-block;vertical-align:middle;width:92px;height:auto;margin-right:10px" />
                  <img src="cid:vigidesastres-logo" alt="Vigidesastres"
                       style="display:inline-block;vertical-align:middle;width:46px;height:auto" />
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr><td style="padding:20px">{content}</td></tr>
        <tr>
          <td style="padding:12px 20px 18px;border-top:1px solid #d7e2e5;text-align:center">
            <div style="margin-bottom:8px;color:#073f67;font-size:11px;font-weight:800;letter-spacing:.08em;text-transform:uppercase">
              Assinatura institucional do projeto
            </div>
            <img src="cid:institucional-card"
                 alt="ARARAS MT · SES-MT · CIEVS-MT · Rede CIEVS · Vigidesastres"
                 style="display:block;max-width:760px;width:100%;height:auto;margin:0 auto" />
          </td>
        </tr>
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
    "araras-logo": ARARAS_LOGO_PATH,
    "governo-ses-logo": GOV_SES_LOGO_PATH,
    "rede-cievs-logo": REDE_CIEVS_LOGO_PATH,
    "vigidesastres-logo": VIGIDESASTRES_LOGO_PATH,
    "institucional-card": ALERT_BRAND_CARD_PATH,
}
