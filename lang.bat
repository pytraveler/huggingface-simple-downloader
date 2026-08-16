@echo off
REM ============================================================
REM  Which language the .bat half speaks. Sets LC to "en" or "ru".
REM
REM  Called rather than copied into each script: two files asking the
REM  same question two slightly different ways is exactly the drift
REM  the rest of this project refuses.
REM
REM  Deliberately no setlocal - the whole point is to set LC in the
REM  caller's environment.
REM
REM  Three sources, in order of how deliberate they are, matching what
REM  i18n.pick_lang() does on the Python side:
REM    1. HFDL_LANG in the environment
REM    2. "lang" in settings.json, which is where the RU / EN button writes
REM    3. the Windows UI language, from the registry
REM  Anything unrecognised, and anything missing, means English.
REM
REM  Each source is cleaned and *then* tested for emptiness, which is
REM  the whole reason :clean is a subroutine. settings.json carries
REM  "lang": "" until the RU / EN button has been pressed - that is the
REM  ordinary case, not an edge one - and a value that cleans away to
REM  nothing has to fall through to the next source rather than count
REM  as an answer of "English".
REM ============================================================
set "LC="

if defined HFDL_LANG set "LC=%HFDL_LANG%"
call :clean
if defined LC goto :decide

REM settings.json does not exist until the window has been run once,
REM which is exactly the case install.bat is usually in.
if not exist "%~dp0settings.json" goto :registry
REM A line reads   "lang": "ru",   - token 2 after a colon is the value,
REM quotes, comma and spaces included; :clean strips those.
for /f "usebackq tokens=2 delims=:" %%a in (`findstr /i /c:"\"lang\"" "%~dp0settings.json" 2^>nul`) do set "LC=%%a"
call :clean
if defined LC goto :decide

:registry
REM LocaleName is "ru-RU", "en-US" and so on. The header line of the
REM query has fewer than three tokens and so sets nothing.
for /f "tokens=3" %%a in ('reg query "HKCU\Control Panel\International" /v LocaleName 2^>nul') do set "LC=%%a"
call :clean

:decide
if not defined LC goto :lang_en
if /I "%LC:~0,2%"=="ru" goto :lang_ru

:lang_en
set "LC=en"
goto :eof

:lang_ru
set "LC=ru"
goto :eof

REM ------------------------------------------------------------
REM  Strip the punctuation a JSON value arrives wrapped in, and leave
REM  LC undefined if nothing is left.
REM
REM  Each step is guarded, because substitution on an *undefined*
REM  variable does not clear it - it yields the literal text %LC:"=%
REM  and the next test would pass on that.
REM
REM  The braces are stripped for the same reason as the comma: the file
REM  is normally written with indent=2, one key per line, but a
REM  hand-edited or minified one puts `"lang": "" }` on the value's own
REM  line and the tail would then read as a language.
REM ------------------------------------------------------------
:clean
if not defined LC goto :eof
set LC=%LC:"=%
if not defined LC goto :eof
set LC=%LC:,=%
if not defined LC goto :eof
set LC=%LC:{=%
if not defined LC goto :eof
set LC=%LC:}=%
if not defined LC goto :eof
set LC=%LC: =%
goto :eof
