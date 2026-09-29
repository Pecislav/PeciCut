@echo off
chcp 65001 >nul
title Pecislav Studio
cd /d "%~dp0"

echo Spoustim Pecislav Studio...
where py >nul 2>nul
if %errorlevel% equ 0 (
    py main_gui.py
    goto end
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    python main_gui.py
    goto end
)

echo CHYBA: Python nebyl nalezen v systemu.
echo Nainstalujte prosim Python 3.10 nebo novejsi z https://python.org
pause

:end
