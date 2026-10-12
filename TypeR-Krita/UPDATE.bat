@echo off
rem === TypeR - Update fuer Krita (Windows) ===
rem Kopiert die neuesten Plugin-Dateien ueber eine bestehende Installation.
rem Danach in Krita unten rechts im TypeR-Docker den "Build"-Wert pruefen -
rem er muss zu dem passen, den diese BAT ausgibt. Einfach doppelklicken.
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
for %%F in ("%DEST%\typer_kr\typer_kr.py") do echo    Datum: %%~tF
rem Das Datum allein beweist nichts: copy/xcopy uebernehmen den Zeitstempel
rem der Quelle, und auf einem Sync-Laufwerk schreibt der Client ihn zurueck -
rem eine aktualisierte Datei behaelt dann ein altes Datum. Der Hash nicht.
set "HASH="
for /f "skip=1 delims=" %%H in ('certutil -hashfile "%DEST%\typer_kr\typer_kr.py" SHA1') do if not defined HASH set "HASH=%%H"
set "HASH=%HASH: =%"
echo    Build: %HASH:~0,7%

echo.
echo ============================================
echo   FERTIG - Update eingespielt.
echo ============================================
echo.
echo Starte Krita neu. Im TypeR-Docker unten rechts steht "Build" mit
echo demselben Wert wie oben - sonst laeuft noch der alte Code.
echo.
goto :done

:fail
echo.
echo [ABBRUCH] Update fehlgeschlagen. Krita vorher schliessen und erneut versuchen.
echo.

:done
pause
endlocal
