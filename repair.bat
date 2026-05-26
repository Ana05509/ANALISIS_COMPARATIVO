@echo off
REM Script para reparar el proyecto y verificar que funcione

echo.
echo ======================================
echo REPARADOR DE IMPORTS Y MODULOS
echo ======================================
echo.

echo [1/5] Reparando requirements.txt...
if exist requirements_new.txt (
    copy /Y requirements_new.txt requirements.txt >nul
    del /Q requirements_new.txt
    echo ✓ requirements.txt reparado
) else (
    echo ✓ requirements.txt ya está correcto
)

echo.
echo [2/5] Instalando dependencias...
pip install -r requirements.txt --quiet
if %ERRORLEVEL% EQU 0 (
    echo ✓ Dependencias instaladas correctamente
) else (
    echo ✗ Error al instalar dependencias
    pause
    exit /b 1
)

echo.
echo [3/5] Creando estructura de directorios...
python setup_structure.py
if %ERRORLEVEL% EQU 0 (
    echo ✓ Estructura creada
) else (
    echo ⚠️ Advertencia al crear estructura
)

echo.
echo [4/5] Generando migraciones...
python manage.py makemigrations
if %ERRORLEVEL% EQU 0 (
    echo ✓ Migraciones generadas
) else (
    echo ⚠️ Advertencia al generar migraciones
)

echo.
echo [5/5] Verificando proyecto Django...
python manage.py check
if %ERRORLEVEL% EQU 0 (
    echo.
    echo ======================================
    echo ✓ ¡PROYECTO LISTO PARA USAR!
    echo ======================================
    echo.
    echo Comandos disponibles:
    echo - Migrar BD: python manage.py migrate
    echo - Crear admin: python manage.py createsuperuser
    echo - Ejecutar: python manage.py runserver
    echo.
) else (
    echo ✗ Hay problemas con el proyecto
    pause
    exit /b 1
)

pause
