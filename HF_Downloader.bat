@echo off
REM ============================================================
REM  Open the window. First run installs; every run after that is instant.
REM  Открыть окно. Первый запуск ставит окружение, дальше - мгновенно.
REM
REM  The console stays open behind the window on purpose: it and
REM  downloader.log are the two places an error goes, and a GUI that
REM  vanishes without either is a bug report nobody can answer.
REM ============================================================
chcp 65001 >nul
setlocal

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"
call "%SCRIPT_DIR%lang.bat"

set "SUB=HuggingFace Simple Downloader - opening the window"
if /I "%LC%"=="ru" set "SUB=HuggingFace Simple Downloader - открываю окно"
call "%SCRIPT_DIR%logo.bat" "%SUB%"

set "PY=.venv\Scripts\python.exe"

if not exist "%PY%" (
    call :say "  The environment is not built yet - running install.bat first." "  Окружение ещё не собрано - сначала запускаю install.bat."
    echo.
    call "%SCRIPT_DIR%install.bat"
    if not exist "%PY%" exit /b 1
)

%PY% -m hfdl
if errorlevel 1 (
    echo.
    call :say "  The window closed with an error. See downloader.log next to this file." "  Окно закрылось с ошибкой. Смотрите downloader.log рядом с этим файлом."
    pause
)
exit /b 0

:say
if /I "%LC%"=="ru" goto :say_ru
echo %~1
goto :eof
:say_ru
echo %~2
goto :eof
