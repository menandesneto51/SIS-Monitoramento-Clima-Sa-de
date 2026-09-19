# Regionais de alerta — e-mails ERS oficiais

**Fonte:** `Controle_Indicacoes_El_Nino_SES_MT_2026_ATUALIZADO_ERS_PARTICIPANTES.xlsx`  
aba **Escritorios_Regionais** (export: `data/input/contatos_escritorios_regionais_ers.csv`)  
**Planilha operacional:** `data/input/contatos_alertas_piloto_validacao.csv` (atualizada 2026-09-19)

## Piloto ativo (`ativo=1`)

| Destino | E-mail | Status |
|---------|--------|--------|
| CIEVS Sorriso | `cievs@sorriso.mt.gov.br` | PILOTO_VALIDACAO |
| SMS Sorriso | `saude@sorriso.mt.gov.br` | PILOTO_VALIDACAO |
| SMS / Vigidesastre Cuiabá | `gab.sms@…` / `vigidesastrescuiaba@…` | PILOTO_VALIDACAO |
| ERS Baixada Cuiabana (+ vig/ats) | `ersbc@ses.mt.gov.br` | APROVADO |

## Cadastro estadual — 16 ERS

**Aceite CIEVS:** 2026-09-19 — todos os e-mails institucionais com **`ativo=1`** (`APROVADO_CIEVS_20260919`).

| ERS | E-mail | ativo |
|-----|--------|:----:|
| Água Boa | ersab@ses.mt.gov.br | 1 |
| Alta Floresta | bkp2.ersaf@ses.mt.gov.br | 1 |
| Baixada Cuiabana | ersbc@ses.mt.gov.br | 1 |
| Barra do Garças | ersbg@ses.mt.gov.br | 1 |
| Cáceres | erscac@ses.mt.gov.br | 1 |
| Colíder | erscol@ses.mt.gov.br | 1 |
| Diamantino | ersdto@ses.mt.gov.br | 1 |
| Juara | ersjra@ses.mt.gov.br | 1 |
| Juína | ersjna@ses.mt.gov.br | 1 |
| Peixoto de Azevedo | erspaz@ses.mt.gov.br | 1 |
| Pontes e Lacerda | erspl@ses.mt.gov.br | 1 |
| Porto Alegre do Norte | erspan@ses.mt.gov.br | 1 |
| Rondonópolis | ersroo@ses.mt.gov.br | 1 |
| São Félix do Araguaia | erssfa@ses.mt.gov.br | 1 |
| Sinop | erssnp@ses.mt.gov.br | 1 |
| Tangará da Serra | ersts@ses.mt.gov.br | 1 |

## Ativação

1. Prévia sem SMTP: `scripts/homologar_alertas_preview.py` — OK
2. Envio piloto: `scripts/enviar_alertas_piloto_validacao.py --send --force`
3. Scheduler: `docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile alertas up -d alerts-scheduler`
