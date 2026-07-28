@echo off
rem === TypeR - Update fuer Krita (Windows) ===
rem Kopiert die neuesten Plugin-Dateien ueber eine bestehende Installation.
rem Danach in Krita unten rechts im TypeR-Docker die "Build"-Zeit pruefen -
rem sie zeigt den Stand der geladenen Datei. Einfach doppelklicken.
setlocal enableextensions
chcp 65001 >nul

set "SRC=%~dp0"
set "DEST=%APPDATA%\krita\pykrita"

echo ============================================
echo   TypeR - Update
echo ============================================
echo.
echo Ziel: %DEST%
echo.

if not exist "%SRC%typer_kr.desktop" (
  echo [FEHLER] typer_kr.desktop nicht gefunden. Diese BAT muss im TypeR-Krita-Ordner liegen.
  goto :fail
)
if not exist "%SRC%typer_kr\" (
  echo [FEHLER] Ordner "typer_kr" nicht gefunden.
  goto :fail
)
if not exist "%DEST%\typer_kr\" (
  echo Noch nicht installiert - starte stattdessen INSTALL.bat ...
  call "%SRC%INSTALL.bat"
  goto :eof
)

echo Kopiere typer_kr.desktop ...
copy /Y "%SRC%typer_kr.desktop" "%DEST%\" >nul
if errorlevel 1 goto :fail

echo Kopiere Ordner typer_kr ...
xcopy /E /I /Y "%SRC%typer_kr" "%DEST%\typer_kr\" >nul
if errorlevel 1 goto :fail

echo Build der installierten Datei:
for %%F in ("%DEST%\typer_kr\typer_kr.py") do echo    %%~tF

echo.
echo ============================================
echo   FERTIG - Update eingespielt.
echo ============================================
echo.
echo Starte Krita neu. Im TypeR-Docker unten rechts steht "Build <Zeit>" -
echo diese Zeit muss zur gerade kopierten Datei oben passen.
echo.
goto :done

:fail
echo.
echo [ABBRUCH] Update fehlgeschlagen. Krita vorher schliessen und erneut versuchen.
echo.

:done
pause
endlocal
