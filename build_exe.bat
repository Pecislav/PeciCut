@echo off
chcp 65001 >nul
title Pecislav Studio - Vytváření instalace .EXE
cd /d "%~dp0"

echo ========================================================
echo       PECISLAV STUDIO - SESTAVENI SOUBORU .EXE
echo ========================================================
echo.

where py >nul 2>nul
if %errorlevel% equ 0 (
    set PYCMD=py
    goto found_py
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    set PYCMD=python
    goto found_py
)

echo [CHYBA] Python nebyl v systemu nalezen!
echo Nainstalujte prosim Python 3.10 nebo novejsi.
pause
exit /b 1

:found_py
echo [1/3] Kontrola a instalace pozadovanych knihoven...
%PYCMD% -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [VAROVANI] Nektere balicky se nezdarilo nainstalovat, pokracuji...
)

echo.
echo [2/3] Sestavovani Pecislav Studio pomoci PyInstalleru...
%PYCMD% -m PyInstaller --noconfirm PecislavStudio.spec

if %errorlevel% neq 0 (
    echo.
    echo [CHYBA] Sestaveni selhalo! Prohlednete si chybove hlasky vyse.
    pause
    exit /b 1
)

echo.
echo [3/3] Hotovo!
echo Aplikace byla uspesne sestavena do slozky:
echo dist\Pecislav Studio\Pecislav Studio.exe
echo.
echo Muzete celou slozku 'dist\Pecislav Studio' zazipovat a distribuovat!
echo ========================================================
pause
