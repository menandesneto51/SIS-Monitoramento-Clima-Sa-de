# Cutover STI — checklist executável (servidor SES 10.15.0.131)

Rodar **no servidor SES** (disco local, não OneDrive), com Docker e `.env` de produção.

**Tag de freeze:** `prod-fase1-20260919` (branch `operacional-araras-v10`, commit `9ef6aee`).

## Ensaio cutover — host de prova (2026-09-19)

| # | Checagem | Resultado |
|---|----------|-----------|
| Stack overlay prod | `db` + `etl-scheduler` + `app` + `landing` | OK (sem `--profile alertas`) |
| Imagem | `araras-mt:prod` rebuildada no tag | OK |
| `/healthz` | 200 | OK |
| Smoke | `APROVADO_FASE1_COM_RESSALVAS` | Soft: `ehf_fresco` |
| Backup Postgres | `data/backups/sis_clima_saude_20260919_144657.sql.gz` | OK (~33 MB) |
| Deploy `10.15.0.131` | Aguardando STI (sem acesso SSH deste agente) | PENDENTE STI |

```powershell
# 1) Ir ao clone no disco local do servidor
Set-Location C:\araras-mt   # ajustar caminho STI

# 2) Puxar freeze
git fetch origin
git checkout operacional-araras-v10
git pull origin operacional-araras-v10
git checkout prod-fase1-20260919

# 3) Confirmar flags críticas no .env (não versionar)
# DATABASE_URL=postgresql+psycopg2://...@db:5432/sis_clima_saude
# DATABASE_STRICT_POSTGRES=true
# SEND_ALERT_ON_LEVEL_CHANGE=false  # até piloto CIEVS
# Piloto: SEND/FANOUT + ALERT_CONTACTS_CSV=*piloto* + FORCE_ONLY

# 4) Subir stack PRODUÇÃO (overlay imutável + Postgres estrito)
docker compose -f docker-compose.yml -f docker-compose.prod.yml build
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d db etl-scheduler app landing
# Alertas reais só após aceite CIEVS + EHF fresco:
# docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile alertas up -d alerts-scheduler
# NÃO: docker volume prune

# 5) Backup + smokes
$py = "$env:LOCALAPPDATA\araras-mt-venv\Scripts\python.exe"
& $py scripts\backup_postgres_homologacao.py
& $py scripts\smoke_homologacao_producao.py --url http://127.0.0.1:8501
& $py scripts\smoke_ops.py

# 6) Assinar atas
# docs/ATA_ACEITE_HOMOLOGACAO_FASE1.md
# docs/ATA_ACEITE_HOMOLOGACAO_FASE2_ALERTAS.md
```

**Bloqueio residual deste host de prova:** o agente não executa o deploy em `10.15.0.131` sem acesso STI à máquina. Pacote + tag + ensaio local estão prontos.

Referência: `docs/STI_IMPLANTACAO_SERVIDOR_SES.md` · `docs/RELEASE_PRODUCAO.md`
