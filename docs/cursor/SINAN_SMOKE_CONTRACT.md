# Cursor — contrato Sinan para intoxicação por fumaça

## Branch
`feature/sinan-smoke-contract`

## Objetivo
Confirmar o schema real de `dbo.VW_SINAN_INTOXICACAOEXOGENA` antes de alterar a query produtiva.

## Arquivos
- `sql/dw_sinan_intoxicacao_schema_discovery.sql`
- `scripts/validate_sinan_smoke_contract.py`
- `sql/dw_sinan_agravos_calor.sql` — **não alterar ainda**

## Execução no Cursor

Com o `.env` do DW configurado:

```powershell
python scripts/validate_sinan_smoke_contract.py
```

O script deve retornar os grupos:
- NOTIFICATION
- AGENT
- ROUTE
- CIRCUMSTANCE

## Critério para avançar
Só alterar `dw_sinan_agravos_calor.sql` depois de:
1. confirmar nomes reais das colunas;
2. mapear as colunas reais para os nomes normalizados esperados downstream:
   - `agente_tox`
   - `out_agente`
   - `via_1`
   - `via_2`
   - `via_3`
   - `circunstan`
   - `circun_des`
3. testar registros positivos e negativos;
4. revisar com Data Governance e especialista de domínio.

## Regra epidemiológica
Não contar toda intoxicação exógena como fumaça.

O consumidor downstream exige combinação explícita de:
- agente `14 - Outros`;
- descrição contendo fumaça;
- via respiratória;
- circunstância compatível com queimadas/incêndios.

## Segurança
Não imprimir connection string, usuário ou senha.
