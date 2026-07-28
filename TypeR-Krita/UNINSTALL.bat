@echo off
rem === TypeR - Deinstallieren ===
setlocal enableextensions
chcp 65001 >nul

set "DEST=%APPDATA%\krita\pykrita"

echo TypeR - Deinstallation
echo Ordner: %DEST%
echo.

if exist "%DEST%\typer_kr.desktop" (
  del /F /Q "%DEST%\typer_kr.desktop"
  echo Entfernt: typer_kr.desktop
) else (
  echo typer_kr.desktop war nicht vorhanden.
)

if exist "%DEST%\typer_kr\" (
  rmdir /S /Q "%DEST%\typer_kr"
  echo Entfernt: Ordner typer_kr
) else (
  echo Ordner typer_kr war nicht vorhanden.
)

echo.
echo Fertig. Krita neu starten, damit die Aenderung wirkt.
echo.
pause
endlocal
