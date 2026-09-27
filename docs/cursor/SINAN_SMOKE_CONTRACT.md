# Cursor — contrato Sinan para intoxicação por fumaça

## Branch
`feature/sinan-smoke-contract`

## Objetivo
Confirmar o schema real de `dbo.VW_SINAN_INTOXICACAOEXOGENA` antes de alterar a query produtiva.

## Arquivos
- `sql/dw_sinan_intoxicacao_schema_discovery.sql`
- `config/sinan_smoke_contract.json`
- `scripts/validate_sinan_smoke_contract.py`
- `tests/test_sinan_smoke_contract.py`
- `sql/dw_sinan_agravos_calor.sql` — **não alterar ainda**

## Fluxo no Cursor

### 1. Executar discovery
Com o `.env` do DW configurado:

```powershell
python scripts/validate_sinan_smoke_contract.py
```

Na primeira execução o retorno esperado é `SMOKE_CONTRACT_SCHEMA=PENDING`, porque o mapping começa vazio.

### 2. Inspecionar as colunas descobertas
Use o resultado da consulta de schema e identifique manualmente as colunas reais que correspondem a:
- número da notificação;
- data;
- município/código IBGE;
- grupo do agente tóxico;
- descrição do agente;
- vias 1, 2 e 3;
- circunstância;
- descrição da circunstância.

### 3. Preencher mapping explícito
Editar:

`config/sinan_smoke_contract.json`

Cada chave normalizada deve apontar para o **nome real confirmado** da coluna na view.

Não usar aproximação, fuzzy matching ou coluna “parecida”.

### 4. Revalidar
Executar novamente:

```powershell
python scripts/validate_sinan_smoke_contract.py
pytest tests/test_sinan_smoke_contract.py -q
```

Só avançar se:

`SMOKE_CONTRACT_SCHEMA=VALIDATED`

### 5. Alterar a query produtiva
Depois da validação, atualizar apenas o bloco de `VW_SINAN_INTOXICACAOEXOGENA` em:

`sql/dw_sinan_agravos_calor.sql`

Expor aliases normalizados:
- `agente_tox`
- `out_agente`
- `via_1`
- `via_2`
- `via_3`
- `circunstan`
- `circun_des`

Preservar compatibilidade do UNION e demais fontes.

## Regra epidemiológica
Não contar toda intoxicação exógena como fumaça.

O consumidor downstream exige combinação explícita de:
- agente `14 - Outros`;
- descrição contendo fumaça;
- via respiratória;
- circunstância compatível com queimadas/incêndios.

## Agentes obrigatórios
- Data Architect
- Data Governance
- Domain Specialist / Saúde Ambiental
- Security
- QA
- Chief Architect

## Segurança
- não imprimir connection string;
- não imprimir usuário/senha;
- não versionar `.env`;
- discovery é somente leitura.

## Gate
A query produtiva permanece bloqueada enquanto o mapping estiver `pending`.
