# Destinatários de alertas — ARARAS MT

## Arquivo oficial

`data/input/ARARAS_MT_Destinatarios_Alertas_2026.xlsx`  
Fonte pública: [COSEMS-MT — Secretarias](https://cosemsmt.org.br/secretarias/) (coleta 2026-08-10).

Abas:
- **Resumo** — cobertura e regras
- **COSEMS_2026_Raw** — base original
- **Destinatarios_Alertas** — 142 SMS (iniciam PENDENTE / não habilitados)
- **Cobertura_Regional** — 16 regiões
- **Regras_Roteamento** — CIEVS estadual + fan-out territorial + Cuiabá

## Regras de roteamento

| Escopo | Destinatário | Condição |
|--------|--------------|----------|
| Estadual | `menandesneto@ses.mt.gov.br` + `notifica@ses.mt.gov.br` via `ALERT_EMAIL_TO` | Alerta estadual (canal SES/CIEVS) |
| Regional | SMS dos municípios da região envolvida | Só municípios impactados |
| Municipal Cuiabá | `gab.sms@cuiaba.mt.gov.br` | Alerta específico |
| Demais SMS | 1 e-mail/município | Só se envolvido + **APROVADO** |

## Como usar no sistema

```bash
python scripts/import_destinatarios_alertas.py
```

Gera `data/input/contatos_alertas.csv` (gitignored).  
Com `ALERT_FANOUT_ENABLED=true`, o fan-out envia **somente** `ativo=1` / `APROVADO`.

Para liberar um município: na planilha, altere **Validação operacional** para `APROVADO` e rode o import de novo.
