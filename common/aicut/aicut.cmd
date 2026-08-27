@echo off
setlocal

set "ROOT=%~dp0"
set "EXE=%ROOT%build\Debug\AIVideoEditor.exe"

if not exist "%EXE%" (
    set "EXE=%ROOT%build\AIVideoEditor.exe"
)

if not exist "%EXE%" (
    echo Error: AIVideoEditor executable was not found.
    echo.
    echo Build first with:
    echo   cmake -S . -B build
    echo   cmake --build build
    exit /b 1
)

"%EXE%" %*
exit /b %ERRORLEVEL%
