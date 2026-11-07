@echo off
setlocal
cd /d "%~dp0"
if not defined PYTHON set "PYTHON=python"
if not defined PNPM set "PNPM=pnpm.cmd"
if not defined ISCC set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
%PYTHON% -m pip install -r requirements-lock.txt
if errorlevel 1 exit /b 1
pushd frontend
call %PNPM% install --frozen-lockfile
if errorlevel 1 exit /b 1
call %PNPM% test
if errorlevel 1 exit /b 1
call %PNPM% build
if errorlevel 1 exit /b 1
popd
%PYTHON% -m pytest -q
if errorlevel 1 exit /b 1
%PYTHON% -m ruff check server tests migrations launcher.py
if errorlevel 1 exit /b 1
%PYTHON% -m PyInstaller --noconfirm --clean --onedir --name QRPointServer --add-data "frontend/dist;frontend/dist" --add-data "migrations;migrations" --collect-all alembic --collect-all qrcode --hidden-import uvicorn.protocols.http.httptools_impl launcher.py
if errorlevel 1 exit /b 1
copy /y *.bat dist\QRPointServer\ >nul
copy /y config.example.json dist\QRPointServer\ >nul
copy /y README.md dist\QRPointServer\ >nul
"%ISCC%" installer\setup.iss
if errorlevel 1 exit /b 1
echo Build complete: dist\QRPointServer and dist\Setup.exe
