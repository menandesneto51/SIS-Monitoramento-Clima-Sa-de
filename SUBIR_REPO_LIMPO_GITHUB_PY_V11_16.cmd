@echo off
setlocal
chcp 65001 >nul

echo ============================================================
echo SUBIR REPOSITORIO LIMPO PARA GITHUB - PY V11.16
echo ============================================================
echo Este comando deve rodar DENTRO da pasta:
echo SIS-Monitoramento-Clima-Saude-GITHUB-LIMPO
echo.
echo Pasta atual:
cd
echo.

for %%I in ("%CD%") do set "CURR=%%~nxI"
if /I not "%CURR%"=="SIS-Monitoramento-Clima-Saude-GITHUB-LIMPO" (
    echo ERRO: voce NAO esta na pasta limpa.
    echo Entre na pasta limpa antes de rodar este script.
    pause
    exit /b 1
)

git status --short

echo.
echo A lista deve conter apenas codigo, docs, pages, sisclima, config, data/geo, data/processed, data/sample, requirements e README.
echo.
pause

git add .
git diff --cached --name-only > _staged_files.txt

echo.
echo Verificando arquivos proibidos no stage...
findstr /i /r "\.env$ secrets\.toml data/output data/local \.db$ \.sqlite$ \.sqlite3$ \.zip$ logs contatos" _staged_files.txt
if not errorlevel 1 (
    echo.
    echo ERRO: ha arquivo proibido no stage. Commit cancelado.
    type _staged_files.txt
    pause
    exit /b 1
)

echo.
echo Status final do que sera commitado:
git status --short
echo.
pause

git commit -m "ARARAS MT - versao limpa para Streamlit"
if errorlevel 1 (
    echo AVISO: commit pode nao ter ocorrido, talvez nao haja mudancas.
)

git remote remove origin 2>nul
git remote add origin "https://github.com/menandesneto51/SIS-Monitoramento-Clima-Sa-de"
git push -u origin main

echo.
pause
endlocal
