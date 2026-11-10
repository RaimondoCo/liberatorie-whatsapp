@echo off
rem WINDOWS: doppio clic su questo file e parte tutto.
rem La prima volta ci mette un minuto: si installa da sola quello che le serve.
setlocal
cd /d "%~dp0"

set "VENV=%LOCALAPPDATA%\Liberatorie-classe\venv"

rem Cerca Python. Il modo affidabile e' il comando py, che viene installato
rem insieme a Python da python.org.
set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto trovato
where python >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto trovato
goto nopython

:trovato
if exist "%VENV%\Scripts\python.exe" goto avvia

echo Prima volta: preparo l'ambiente, ci vuole un minuto.
%PY% -m venv "%VENV%"
if errorlevel 1 goto nopython
"%VENV%\Scripts\python.exe" -m pip install --quiet --upgrade pip
"%VENV%\Scripts\python.exe" -m pip install --quiet reportlab
if errorlevel 1 goto nointernet
echo Pronto.

:avvia
rem Legge gli screenshot con Tesseract OCR, installato sul computer.
"%VENV%\Scripts\python.exe" genera.py %*
echo.
pause
exit /b 0

:nopython
echo.
echo Su questo computer manca Python, e serve per far funzionare il programma.
echo.
echo 1. Vai su     https://www.python.org/downloads/windows/
echo 2. Scarica    "Windows installer (64-bit)" della versione piu' recente
echo 3. Aprilo e, nella prima schermata, metti la spunta su
echo    "Add python.exe to PATH". Questo passaggio e' quello che conta.
echo 4. Premi "Install Now" e aspetta la fine
echo 5. Chiudi questa finestra e fai di nuovo doppio clic su Liberatoria.bat
echo.
pause
exit /b 1

:nointernet
echo.
echo Installazione fallita: serve una connessione a internet.
echo Riprova quando sei in rete.
echo.
pause
exit /b 1
