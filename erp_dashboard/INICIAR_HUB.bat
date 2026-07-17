@echo off
title G2 Analytics - Hub
cd /d "%~dp0"

echo ====================================================
echo   G2 Analytics Hub
echo ====================================================
echo.

rem ── Python instalado? ───────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado no PATH.
    echo Instale o Python 3.13+ marcando "Add python.exe to PATH"
    echo e rode este arquivo novamente.
    echo.
    pause
    exit /b 1
)

rem ── Dependencias instaladas? (checa as essenciais) ──
python -c "import pandas, fastapi, uvicorn, pyodbc" >nul 2>&1
if errorlevel 1 (
    echo Primeira execucao nesta maquina: instalando dependencias...
    echo ^(isso acontece so uma vez e pode levar alguns minutos^)
    echo.
    python -m pip install --upgrade pip >nul 2>&1
    python -m pip install pyodbc pandas fastapi "uvicorn[standard]" requests customtkinter matplotlib
    if errorlevel 1 (
        echo.
        echo [ERRO] Falha ao instalar dependencias. Verifique a conexao
        echo com a internet e rode novamente.
        pause
        exit /b 1
    )
    echo.
    echo Dependencias instaladas com sucesso!
    echo.
)

echo ====================================================
echo   Iniciando o hub...
echo   (mantenha esta janela aberta enquanto estiver em uso)
echo   Lembrete: esta maquina precisa do ODBC Driver 18 e
echo   do DSN de Sistema "blue_penha" configurados.
echo ====================================================
echo.

python hub\run_hub.py

echo.
echo ----------------------------------------------------
echo   O hub foi encerrado.
echo   Se houver erro acima, anote a mensagem.
echo ----------------------------------------------------
pause >nul
