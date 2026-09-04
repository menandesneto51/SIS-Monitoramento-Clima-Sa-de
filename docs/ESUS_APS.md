# e-SUS APS — Centralizador Postgres (SES/MT)

Fonte **externa, somente leitura**. Não substitui o Postgres operacional do ARARAS (`DATABASE_URL`).

| Item | Valor |
|---|---|
| SGBD | PostgreSQL |
| Host | `10.15.0.25` |
| Banco | `esus2` |
| Porta | `5432` (sonda tenta `5433` se a padrão falhar) |
| Rede | interna SES (`10.15.0.0/16`) — VPN no notebook ou servidor de produção |

O Data Warehouse SQL Server (`10.15.1.50`) **não** tem views `VW_ESUS_*`. Atendimentos e nebulizações da APS saem deste Centralizador.

## Credenciais

Preencha no `.env` local (nunca no Git):

```env
USE_ESUS_APS=true
ESUS_APS_HOST=10.15.0.25
ESUS_APS_PORT=5432
ESUS_APS_DATABASE=esus2
ESUS_APS_USER=
ESUS_APS_PASSWORD=
ESUS_APS_SSLMODE=disable
```

Aliases aceitos: `ESUS_HOST`, `ESUS_DB`, `ESUS_USER`, `ESUS_PASSWORD`. Não use `DATABASE_URL` / `DB_HOST` para este banco.

## Sonda (conexão + inventário)

Com a VPN SES ligada:

```powershell
.\.venv\Scripts\python.exe scripts\explorar_esus_aps.py
```

A sonda:

1. testa TCP `5432` e, se preciso, `5433`;
2. autentica e lê `version()`, `current_database()`, `current_user`;
3. lista schemas/tabelas;
4. classifica cubo Centralizador (`tb_fat_*` + `tb_dim_*`) versus PEC (`tb_cidadao`, `tb_atend`);
5. para tabelas relevantes, grava colunas, `reltuples` e intervalo de datas **sem** selecionar nome, CPF, CNS ou endereço.

Saída local (gitignored): `docs/esus_aps_exploracao.json` e `docs/esus_aps_exploracao.md`.

## Indicadores candidatos (a confirmar no inventário)

| Família | Tabelas típicas | Uso |
|---|---|---|
| Atendimento individual | `tb_fat_atendimento_individual` | Volume APS 7d/28d; CID respiratório / calor |
| Procedimentos | `tb_fat_procedimentos` | Nebulização SIGTAP `0301100039` e `0301100047` |
| Cadastro | `tb_fat_cad_individual` | Proxy de vulneráveis (não substitui busca ativa municipal) |
| Visita ACS | `tb_fat_visita_domiciliar` | Intensidade de território em municípios vermelho/roxo |
| Dimensões | `tb_dim_municipio`, `tb_dim_tempo`, `tb_dim_cid` | Cruzar IBGE-7 com o painel |

## Carga agregada (clima)

Com VPN e `.env` preenchido:

```powershell
.\.venv\Scripts\python.exe scripts\atualizar_esus_aps.py
```

Grava no banco operacional do ARARAS (não no Centralizador):

- `ops_esus_aps_municipio` — volume 7d/28d, CID respiratório/calor/DDA, CIAP respiratório, nebulização SIGTAP `0301100039`/`0301100047`, encaminhamentos
- `ops_esus_aps_cadastro_municipio` — gestante, asma, DPOC, fumante, HAS, DM, acamado, domiciliado, comunidade tradicional, deficiência, idoso 60+

Recorte: `co_ibge` de Mato Grosso (`51`). Sem nome, CPF, CNS ou endereço.

Municípios **vermelho/roxo** do ARARAS entram em `ops_esus_aps_prioridade` (cadastro + pressão APS). A Sala de Situação / Plano El Niño lista os 20 primeiros no briefing.

Contagem operacional da APS — não é incidência nem diagnóstico.

## Atualidade / atraso do Centralizador

A carga de **atendimentos** depende de `tb_fat_atendimento_individual` estar atualizada.
O **cadastro** (`tb_fat_cad_individual`) pode cobrir os 142 municípios mesmo quando o cubo de
atendimento está atrasado.

Se `MAX(dt_inicial_atendimento)` (excluindo datas futuras inválidas) estiver atrasada em mais de
3 dias em relação à data de referência, o ARARAS **ancora** as janelas 7d/28d nessa última data
válida e registra `atraso_dias` / `janela_ancorada` no resumo e no boletim.

Correção definitiva: STI/equipe e-SUS restaurar a réplica/ETL do `esus2` (host `10.15.0.25`).

## LGPD

Extração só agregada (município × janela). A sonda e a carga não fazem dump de cidadão.
