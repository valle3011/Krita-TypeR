@echo off
rem === TypeR - Installer fuer Krita (Windows) ===
rem Kopiert das Plugin in Kritas pykrita-Ordner. Einfach doppelklicken.
setlocal enableextensions
chcp 65001 >nul

set "SRC=%~dp0"
set "DEST=%APPDATA%\krita\pykrita"

echo ============================================
echo   TypeR - Installation
echo ============================================
echo.
echo Quelle: %SRC%
echo Ziel:   %DEST%
echo.

if not exist "%SRC%typer_kr.desktop" (
  echo [FEHLER] typer_kr.desktop nicht gefunden.
  goto :fail
)
if not exist "%SRC%typer_kr\" (
  echo [FEHLER] Ordner "typer_kr" nicht gefunden.
  goto :fail
)

if not exist "%DEST%" (
  echo Erstelle Ordner: %DEST%
  mkdir "%DEST%"
  if errorlevel 1 goto :fail
)

echo Kopiere typer_kr.desktop ...
copy /Y "%SRC%typer_kr.desktop" "%DEST%\" >nul
if errorlevel 1 goto :fail

echo Kopiere Ordner typer_kr ...
xcopy /E /I /Y "%SRC%typer_kr" "%DEST%\typer_kr\" >nul
if errorlevel 1 goto :fail

echo.
echo ============================================
echo   FERTIG - Plugin ist installiert.
echo ============================================
echo.
echo In Krita: Einstellungen - Krita einrichten - Python-Plugin-Manager -
echo Haken bei "TypeR for Krita" - Krita neu starten.
echo Der Docker liegt unter Einstellungen - Andockbare Dialoge - "TypeR".
echo.
goto :done

:fail
echo.
echo [ABBRUCH] Installation fehlgeschlagen. Krita vorher schliessen und erneut versuchen.
echo.

:done
pause
endlocal
