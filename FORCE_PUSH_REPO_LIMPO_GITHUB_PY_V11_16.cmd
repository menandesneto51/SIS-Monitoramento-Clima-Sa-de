@echo off
setlocal
chcp 65001 >nul

echo ============================================================
echo FORCE PUSH REPOSITORIO LIMPO - PY V11.16
echo ============================================================
echo Use somente DENTRO da pasta limpa e apenas se quiser substituir
echo o conteudo remoto pela versao limpa.
echo.
pause

for %%I in ("%CD%") do set "CURR=%%~nxI"
if /I not "%CURR%"=="SIS-Monitoramento-Clima-Saude-GITHUB-LIMPO" (
    echo ERRO: voce NAO esta na pasta limpa.
    pause
    exit /b 1
)

git remote remove origin 2>nul
git remote add origin "https://github.com/menandesneto51/SIS-Monitoramento-Clima-Sa-de"
git fetch origin main
git push -u origin main --force-with-lease

echo.
pause
endlocal
