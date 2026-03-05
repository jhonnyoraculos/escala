@echo off
setlocal

REM ---------------------------------------------------------------------------
REM Script de build do JR Escala
REM ---------------------------------------------------------------------------

cd /d "%~dp0"

REM Validação de arquivos de dados necessários
set "MISSING_DATA="
if not exist "jr_escala.db" (
    echo [ERRO] Arquivo "jr_escala.db" não encontrado na pasta atual.
    set "MISSING_DATA=1"
)
if not exist "logo-jr.png" (
    echo [ERRO] Arquivo "logo-jr.png" não encontrado na pasta atual.
    set "MISSING_DATA=1"
)
if not exist "icone.png" (
    echo [ERRO] Arquivo "icone.png" não encontrado na pasta atual.
    set "MISSING_DATA=1"
)
if not exist "relatorios" (
    echo [AVISO] Pasta "relatorios" não encontrada. Criando automaticamente...
    mkdir "relatorios" >nul 2>&1
)
if not exist "fotos_colaboradores" (
    echo [AVISO] Pasta "fotos_colaboradores" não encontrada. Criando automaticamente...
    mkdir "fotos_colaboradores" >nul 2>&1
)
if defined MISSING_DATA (
    echo Corrija os arquivos ausentes e execute novamente.
    exit /b 1
)

REM Limpeza de artefatos antigos
if exist build  rmdir /s /q build
if exist dist   rmdir /s /q dist

REM Detecta o launcher do Python
set "PYTHON_LAUNCHER="
where py >nul 2>&1
if %errorlevel%==0 set "PYTHON_LAUNCHER=py"

if not defined PYTHON_LAUNCHER (
    where python >nul 2>&1
    if %errorlevel%==0 set "PYTHON_LAUNCHER=python"
)

if not defined PYTHON_LAUNCHER (
    if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\py.exe" (
        set "PYTHON_LAUNCHER=%LOCALAPPDATA%\Microsoft\WindowsApps\py.exe"
    ) else if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe" (
        set "PYTHON_LAUNCHER=%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe"
    )
)

if not defined PYTHON_LAUNCHER (
    echo [ERRO] Nenhum Python encontrado no PATH.
    echo Instale o Python 3 ou habilite o App Execution Alias em Configuracoes > Aplicativos.
    exit /b 1
)

REM Define argumentos do PyInstaller (preferindo o .spec)
set "SPEC_FILE=JR_Escala.spec"
set "PYINSTALLER_ARGS="
if exist "%SPEC_FILE%" (
    echo [INFO] Usando arquivo de especificação "%SPEC_FILE%".
    set "PYINSTALLER_ARGS=%SPEC_FILE%"
) else (
    echo [INFO] Arquivo .spec não encontrado. Aplicando parâmetros inline.
    set "PYINSTALLER_ARGS=--clean --noconfirm --onedir --name JR_Escala --icon icone.png --add-data \"jr_escala.db;jr_escala.db\" --add-data \"logo-jr.png;logo-jr.png\" --add-data \"relatorios;relatorios\" --add-data \"fotos_colaboradores;fotos_colaboradores\" jr_escala.py"
)

echo [INFO] Iniciando build (saída completa em build_log.txt)...
"%PYTHON_LAUNCHER%" -m PyInstaller %PYINSTALLER_ARGS% > build_log.txt 2>&1
if errorlevel 1 (
    echo [ERRO] O build falhou. Consulte build_log.txt para detalhes.
    exit /b 1
)

echo [SUCESSO] Build finalizado. Executável em dist\JR_Escala\JR_Escala.exe

endlocal
