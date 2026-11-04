@echo off
rem SAKRA - sestaveni pro Windows: slozka dist\SAKRA (PyInstaller) a instalator (Inno Setup 6)
cd /d "%~dp0\.."
where uv >nul 2>nul || (echo Chybi nastroj uv: https://docs.astral.sh/uv/ & pause & exit /b 1)
uv sync || goto chyba
uv run --with pyinstaller pyinstaller --noconfirm --clean instalator\sakra.spec || goto chyba
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist %ISCC% (
  %ISCC% instalator\sakra.iss || goto chyba
) else (
  echo Inno Setup 6 neni nainstalovany - hotova je jen slozka dist\SAKRA
)
echo Hotovo.
pause
exit /b 0
:chyba
echo Sestaveni selhalo.
pause
exit /b 1
