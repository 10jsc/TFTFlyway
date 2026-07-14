@echo off
title TFTFlyway - Modo Automático
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo.
echo  ========================================
echo    🛡️  TFTFlyway - Iniciando Monitor
echo  ========================================
echo.
python -u monitor.py
pause
