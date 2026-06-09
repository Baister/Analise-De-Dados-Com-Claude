@echo off
title G2 Analytics - Hub
cd /d "%~dp0"

echo ====================================================
echo   Iniciando o G2 Analytics Hub...
echo   (mantenha esta janela aberta enquanto estiver em uso)
echo ====================================================
echo.

python hub\run_hub.py

echo.
echo ----------------------------------------------------
echo   O hub foi encerrado.
echo   Se houver erro acima, anote a mensagem.
echo ----------------------------------------------------
pause >nul
