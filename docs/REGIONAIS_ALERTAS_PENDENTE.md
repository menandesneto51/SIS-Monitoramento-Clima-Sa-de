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

Todos os e-mails institucionais estão na planilha piloto.  
Os 15 ERS além da Baixada estão com **`ativo=0`** (`CADASTRO_ERS_PENDENTE_ATIVACAO`) até aceite CIEVS por regional — evita fan-out acidental.

| ERS | E-mail | ativo |
|-----|--------|:----:|
| Água Boa | ersab@ses.mt.gov.br | 0 |
| Alta Floresta | bkp2.ersaf@ses.mt.gov.br | 0 |
| Baixada Cuiabana | ersbc@ses.mt.gov.br | 1 |
| Barra do Garças | ersbg@ses.mt.gov.br | 0 |
| Cáceres | erscac@ses.mt.gov.br | 0 |
| Colíder | erscol@ses.mt.gov.br | 0 |
| Diamantino | ersdto@ses.mt.gov.br | 0 |
| Juara | ersjra@ses.mt.gov.br | 0 |
| Juína | ersjna@ses.mt.gov.br | 0 |
| Peixoto de Azevedo | erspaz@ses.mt.gov.br | 0 |
| Pontes e Lacerda | erspl@ses.mt.gov.br | 0 |
| Porto Alegre do Norte | erspan@ses.mt.gov.br | 0 |
| Rondonópolis | ersroo@ses.mt.gov.br | 0 |
| São Félix do Araguaia | erssfa@ses.mt.gov.br | 0 |
| Sinop | erssnp@ses.mt.gov.br | 0 |
| Tangará da Serra | ersts@ses.mt.gov.br | 0 |

## Ativação

1. Prévia sem SMTP: `scripts/homologar_alertas_preview.py`
2. Envio piloto controlado: `docs/PILOTO_ALERTAS_CUIABA_SORRISO.md`
3. Para cada ERS: setar `ativo=1` + `validacao_operacional=APROVADO` após teste de caixa
