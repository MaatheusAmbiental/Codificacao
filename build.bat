@echo off
setlocal enableextensions

echo.
echo =================================================================
echo      BUILD AMBIENTE SEGURO
echo =================================================================
echo.

:: 1. VERIFICAR O PYTHON DO AMBIENTE VIRTUAL ATIVADO
echo [FASE 1/5] Verificando a versao do Python ativa...
python --version
echo.

:: 2. LIMPEZA
echo [FASE 2/5] Limpando ambiente anterior...
if exist "build" rmdir /s /q build
if exist "dist" rmdir /s /q dist
del Codificacao_Hidrologica.spec.bak 2>nul
echo.

:: 3. INSTALAÇÃO DE DEPENDÊNCIAS
echo [FASE 3/5] Instalando dependencias no ambiente atual...
python -m pip install --upgrade pip
:: Garante que as libs críticas para a GUI e o build estejam presentes
python -m pip install pyinstaller PySide6 python-dotenv openpyxl
:: Instala o restante das dependências de geoprocessamento
python -m pip install -r requirements.txt
echo.

:: 4. GERAÇÃO DO EXECUTÁVEL
echo [FASE 4/5] Gerando executavel a partir de 'Codificacao_Hidrologica.spec'...
python -m PyInstaller --noconfirm --clean Codificacao_Hidrologica.spec

if %errorlevel% neq 0 (
    echo.
    echo ERRO CRITICO NA GERACAO DO EXE.
    pause
    exit /b
)
echo.

:: 5. COPIA DE RECURSOS EXTERNOS
:: Codificacao_Hidrologica.spec gera um .exe unico (onefile) -- resource_path() procura
:: 'assets' e 'insumo' no MESMO diretorio do .exe (dist\), nao numa subpasta com o nome dele.
echo [FASE 5/5] Copiando pastas 'assets' e 'insumo' para o diretorio final...
xcopy "assets" "dist\assets" /E /I /Y > nul
if exist "insumo" xcopy "insumo" "dist\insumo" /E /I /Y > nul

echo.
echo =================================================================
echo      CONCLUIDO!
echo      Seu aplicativo esta em 'dist\Codificacao_Hidrologica.exe'.
echo =================================================================
pause
endlocal
