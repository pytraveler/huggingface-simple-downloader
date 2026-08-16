@echo off
REM ============================================================
REM  Install: fetch uv, build the .venv, check tkinter, run the tests.
REM  Установка: скачать uv, собрать .venv, проверить tkinter, прогнать тесты.
REM ============================================================
chcp 65001 >nul
setlocal

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"
REM English or Russian, decided once and used by every :say below.
call "%SCRIPT_DIR%lang.bat"

set "SUB=HuggingFace Simple Downloader - setting up the venv"
if /I "%LC%"=="ru" set "SUB=HuggingFace Simple Downloader - установка venv-окружения"
call "%SCRIPT_DIR%logo.bat" "%SUB%"

REM Full path to uv: cmd does not always agree to look for an .exe in the
REM current folder (NoDefaultCurrentDirectoryInExePath). PY stays relative -
REM there was a cd above.
set "UV=%SCRIPT_DIR%uv.exe"
set "PY=.venv\Scripts\python.exe"

REM ============================================================
REM  Step 1: uv.exe
REM  It is not committed, so a fresh clone has to fetch it. uv does
REM  everything else itself, including bringing along a Python.
REM ============================================================
if exist "%UV%" goto :uv_ok

call :say "[1/4] Downloading uv..." "[1/4] Скачиваю uv..."
if not exist "downloads" mkdir "downloads"
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip' -OutFile 'downloads\uv.zip'"
powershell -NoProfile -Command "Expand-Archive -Path 'downloads\uv.zip' -DestinationPath 'downloads\uv_tmp' -Force"
if exist "downloads\uv_tmp\uv.exe" copy /y "downloads\uv_tmp\uv.exe" "%UV%" >nul
rmdir /s /q "downloads\uv_tmp" 2>nul
del /f /q "downloads\uv.zip" 2>nul
rmdir "downloads" 2>nul
if not exist "%UV%" (
    call :say "  ERROR: could not download uv. Check your internet access." "  ОШИБКА: не удалось скачать uv. Проверьте доступ в интернет."
    pause
    exit /b 1
)
call :say "  [OK] uv.exe downloaded" "  [OK] uv.exe загружен"
goto :uv_done

:uv_ok
call :say "[1/4] uv.exe is already here" "[1/4] uv.exe уже на месте"

:uv_done

REM ============================================================
REM  Step 2: the environment
REM  uv sync reads pyproject.toml and uv.lock: it creates a .venv of the
REM  right Python version, installs httpx and the package itself. Running
REM  it again is harmless.
REM
REM  --managed-python is not decoration. The window needs tkinter, and a
REM  Python that uv found on the machine may well be an embeddable build
REM  or a Store one without it; the interpreter uv brings along always has
REM  it. If the flag is unknown (an old uv.exe from a previous project),
REM  fall back to a plain sync rather than failing.
REM ============================================================
echo.
call :say "[2/4] Building the .venv..." "[2/4] Собираю окружение .venv..."
"%UV%" sync --managed-python
if errorlevel 1 (
    call :say "  retrying without --managed-python..." "  повтор без --managed-python..."
    "%UV%" sync
)
if errorlevel 1 (
    call :say "  ERROR: uv sync failed. See the output above." "  ОШИБКА: uv sync завершился неудачно. Смотрите вывод выше."
    pause
    exit /b 1
)
if not exist "%PY%" (
    call :say "  ERROR: uv finished, but %PY% is not there." "  ОШИБКА: uv отработал, но %PY% не найден."
    pause
    exit /b 1
)
call :say "  [OK] dependencies installed" "  [OK] зависимости установлены"

REM ============================================================
REM  Step 3: tkinter
REM  The whole program is a window. Finding out here that the interpreter
REM  cannot draw one is a message; finding out at launch is a traceback in
REM  a console that closes.
REM ============================================================
echo.
call :say "[3/4] Checking tkinter..." "[3/4] Проверяю tkinter..."
%PY% -c "import tkinter, hfdl; print(hfdl.__version__)" >nul 2>&1
if errorlevel 1 (
    call :say "  ERROR: this Python cannot import tkinter or hfdl." "  ОШИБКА: этот Python не импортирует tkinter или hfdl."
    call :say "  Delete uv.exe and .venv and run install.bat again." "  Удалите uv.exe и .venv и запустите install.bat заново."
    %PY% -c "import tkinter, hfdl"
    pause
    exit /b 1
)
call :say "  [OK] the window can be drawn" "  [OK] окно рисовать есть чем"

REM ============================================================
REM  Step 4: the tests
REM  All offline - no repository is contacted.
REM
REM  Through -m pytest rather than `uv run pytest`: the second form fails
REM  right after the project is rebuilt with 'uv trampoline failed to
REM  canonicalize script path'.
REM ============================================================
echo.
call :say "[4/4] Running the tests..." "[4/4] Прогоняю тесты..."
%PY% -m pytest -q
if errorlevel 1 (
    call :say "  [!] The tests did not pass - it installed, but something is wrong." "  [!] Тесты не прошли - установка состоялась, но что-то не так."
) else (
    call :say "  [OK] the tests passed" "  [OK] тесты прошли"
)

echo.
echo ============================================================
call :say "     Installation finished" "     Установка завершена"
echo.
call :say "  HF_Downloader.bat  - open the window" "  HF_Downloader.bat  - открыть окно"
echo ============================================================
echo.
pause
exit /b 0


REM ============================================================
REM  One line, both languages, at the point that prints it - the same
REM  shape as i18n.Text on the Python side, and for the same reason:
REM  there is no key to go stale between them.
REM
REM  Written with goto rather than `if (...) else (...)` because a message
REM  containing a bracket would close the block early and the rest of the
REM  line would run as a command.
REM ============================================================
:say
if /I "%LC%"=="ru" goto :say_ru
echo %~1
goto :eof
:say_ru
echo %~2
goto :eof
