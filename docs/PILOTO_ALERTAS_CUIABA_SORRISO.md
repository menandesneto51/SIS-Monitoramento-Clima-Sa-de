# Piloto de validação de alertas — SES + Cuiabá + Sorriso

## Pedido original (26/08/2026)

Na conversa [Document rewrite with results](34d1b430-7a66-4752-9530-1d1dc2410f31):

> inserir o email `cievs@sorriso.mt.gov.br` para receber os alertas do município de Sorriso como teste, e retomar os e-mails e Telegram da situação estadual.

Estado encontrado em 15/09/2026:

| Item | Antes |
|------|--------|
| `ALERT_FORCE_MUNICIPIOS` | só `5107925` (Sorriso) |
| `cievs@sorriso.mt.gov.br` na planilha | **ausente** |
| Contatos Cuiabá/Sorriso | `ativo=0` / e-mails genéricos |
| `SEND_ALERT_ON_LEVEL_CHANGE` | `false` (envio central bloqueado) |
| `ALERT_FANOUT_ENABLED` | `false` |
| Regionais | sem e-mail institucional real no CSV |

## Configuração atual (piloto — aceite CIEVS 2026-09-19)

Planilha: `data/input/contatos_alertas_piloto_validacao.csv` (22 contatos `ativo=1`)

| Destino | E-mail |
|---------|--------|
| SES/CIEVS (estadual) | `ALERT_EMAIL_TO` + Telegram central |
| Sorriso | `cievs@sorriso.mt.gov.br`, `saude@sorriso.mt.gov.br` |
| Cuiabá (Vigidesastre) | `vigidesastrescuiaba@gmail.com` |
| Cuiabá (SMS) | `gab.sms@cuiaba.mt.gov.br` |
| 16 ERS | e-mails institucionais `@ses.mt.gov.br` (ver `docs/REGIONAIS_ALERTAS_PENDENTE.md`) |

**Último envio controlado:** 2026-09-19 — digest `enviado` + Cuiabá OK · evidências em `logs/piloto_alertas_validacao/`

Flags (`.env`):

- `SEND_ALERT_ON_LEVEL_CHANGE=true`
- `ALERT_FANOUT_ENABLED=true`
- `ALERT_CONTACTS_CSV=data/input/contatos_alertas_piloto_validacao.csv`
- `ALERT_FORCE_MUNICIPIOS=5103403,5107925`
- `ALERT_FORCE_ONLY=true` (municípios só forçados)
- `ALERT_LAYERS=ses,regionais,municipais,cuiaba`
- `ALERT_MAX_MUNICIPIOS=0`
- `ALERT_CUIABA_SEND=true`
- `ALERT_REQUIRE_FRESH_ETL=true`
- `DATABASE_STRICT_POSTGRES=true`
- `ALERT_ENVIO_MODO=scheduler_piloto`

## Comandos

```powershell
$py = ".\.venv\Scripts\python.exe"
# prévia (sem envio)
& $py scripts\enviar_alertas_piloto_validacao.py
# envio
& $py scripts\enviar_alertas_piloto_validacao.py --send --force
# scheduler contínuo
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile alertas up -d alerts-scheduler
```

Evidências: `logs/piloto_alertas_validacao/`

## Regionais

Para incluir Sinop (regional de Sorriso) e Baixada Cuiabana, acrescentar linhas `tipo_destinatario=regional` com e-mail **real** na planilha piloto e passar `regionais` em `ALERT_LAYERS`. Sem e-mail válido, o sistema **não inventa** destinatário.
