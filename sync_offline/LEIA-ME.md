# Pacote offline — atualização VIGIA (4 categorias)

## Por que este pacote?

Na rede da SES o `git pull` falha com `Could not resolve host: github.com`.
Seu preview ainda mostra **TIPO 1/3** e o script IndicaSUS antigo (~400 linhas) —
isso é código **antigo**. Mudar só o `.env` **não** atualiza o Python.

Este pacote traz os arquivos da branch com:

- Alertas **TIPO 1/4 … 4/4** (estado / regional×16 / municipal / Cuiabá)
- Texto completo no e-mail + ícones + fatiamento Telegram
- IndicaSUS com usuário **Roney** (sem herdar senha DW)
- ODBC Driver 18 com `TrustServerCertificate=yes` (não `true`)
- Loaders DW (SIM/SINAN/GAL/CNES/SIH) + `validar_fontes_dw.py`

## Como aplicar (Windows / OneDrive)

1. Copie a pasta `sync_offline` (ou o ZIP) para o PC da SES, por exemplo:
   `C:\Users\...\Monitoramento ondas de calor\sync_offline\`
2. Abra PowerShell **nessa pasta** e rode:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\aplicar_atualizacao_vigia.ps1
```

Ou apontando o destino:

```powershell
.\aplicar_atualizacao_vigia.ps1 -Destino "C:\Users\Menandesneto\OneDrive\CIEVS MT\Monitoramento ondas de calor"
```

3. Ajuste o `.env` (o script **não** sobrescreve senhas):

```env
INDICASUS_USER=roneydamaceno
INDICASUS_PASSWORD=<senha Roney>
INDICASUS_ENCRYPT=no
INDICASUS_TRUST_SERVER_CERTIFICATE=yes
INDICASUS_USE_DW_CREDENTIALS=false

ALERT_VIGIA_CATEGORIAS=estado,regional,municipal,cuiaba
```

4. Confirme o código novo:

```powershell
Select-String -Path .\sisclima\alerts\vigia_alerts.py -Pattern "TIPO 1/4"
.\.venv\Scripts\python.exe preview_alerta_vigia.py
```

O preview deve mostrar **TIPO 1/4**, não 1/3.

5. IndicaSUS (ocupação):

```powershell
.\.venv\Scripts\python.exe atualizar_ocupacao_indicasus.py --descobrir
```

Se o login ainda for `menandes_cievs`, o `.env` ainda está herdando DW.

6. Fontes DW (indicadores “indisponível”):

```powershell
.\.venv\Scripts\python.exe validar_fontes_dw.py
```

“Indisponível” no alerta = tabela vazia / SQL falhou / SIVEP local sem arquivo.
Corrigir conexão e SQL; depois rodar o ciclo de novo.

7. Teste de alerta **sem flood** (~160 e-mails se municipal estiver ligado):

```env
ALERT_VIGIA_CATEGORIAS=estado,cuiaba
```

```powershell
.\.venv\Scripts\python.exe run_ciclo_completo.py --force-alert
```

## Sobre o erro IndicaSUS que você viu

```
Login failed for user 'menandes_cievs'
Atributo de cadeia de conexão inválido
```

Causas típicas no código **antigo**:

1. Script legado usa senha DW no BdSES.
2. `TrustServerCertificate=true` (ODBC 18 exige `yes`/`no`).

Com este pacote + `.env` acima, o usuário deve ser `roneydamaceno`.

## Backup

O script cria `backup_pre_vigia4_YYYYMMDD_HHMMSS\` com os arquivos substituídos.
