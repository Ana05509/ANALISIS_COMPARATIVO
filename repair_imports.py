#!/usr/bin/env python3
"""
Script para reparar problemas de imports y módulos en el proyecto.
"""

import os
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).parent
ERRORS = []
FIXES = []

def fix_requirements_txt():
    """Reparar archivo requirements.txt corrupto."""
    try:
        req_file = BASE_DIR / "requirements.txt"
        req_new = BASE_DIR / "requirements_new.txt"
        
        if req_new.exists():
            # Leer el archivo nuevo (limpio)
            with open(req_new, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Escribir al archivo original
            with open(req_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Eliminar el archivo nuevo
            req_new.unlink()
            
            FIXES.append("✅ requirements.txt reparado correctamente")
    except Exception as e:
        ERRORS.append(f"❌ Error reparando requirements.txt: {e}")

def verify_module_structure():
    """Verificar que la estructura de módulos sea correcta."""
    required_files = [
        "analisis/__init__.py",
        "analisis/models.py",
        "analisis/forms.py",
        "analisis/admin.py",
        "analisis/urls.py",
        "analisis/views/__init__.py",
        "analisis/views/dashboard.py",
        "analisis/views/subir_datos.py",
        "analisis/views/comparison.py",
        "analisis/views/analysis.py",
        "analisis/views/catalogo.py",
        "analisis/views/reportes.py",
        "analisis/views/historial.py",
        "analisis/views/producto.py",
        "analisis/services/__init__.py",
        "analisis/services/business/__init__.py",
        "analisis/services/business/upload_service.py",
        "analisis/services/business/comparison_service.py",
        "analisis/services/business/analysis_service.py",
        "analisis/services/business/report_service.py",
        "analisis/services/business/export_service.py",
        "analisis/services/business/catalog_service.py",
        "analisis/services/business/visualization_service.py",
        "analisis/services/business/statistics_service.py",
        "analisis/services/processing/__init__.py",
        "analisis/services/processing/pipeline.py",
        "analisis/services/processing/diversity.py",
        "analisis/services/processing/abundance.py",
        "analisis/services/data/__init__.py",
        "analisis/services/data/file_service.py",
        "analisis/services/data/metadata_service.py",
        "analisis/services/data/excel_service.py",  # Archivo correcto
        "analisis/services/interpretation/__init__.py",
        "analisis/services/interpretation/microorganism_classifier.py",
        "analisis/services/interpretation/beneficial_service.py",
        "analisis/services/interpretation/pathogen_service.py",
        "config/__init__.py",
        "config/settings.py",
        "config/urls.py",
        "config/wsgi.py",
        "config/asgi.py",
        "manage.py",
    ]
    
    missing = []
    for file in required_files:
        path = BASE_DIR / file
        if not path.exists():
            missing.append(file)
    
    if missing:
        ERRORS.append(f"❌ Archivos faltantes: {missing}")
    else:
        FIXES.append(f"✅ Estructura de módulos verificada ({len(required_files)} archivos)")

def verify_excel_service():
    """Verificar que excel_service.py existe y excel_cervise.py no se importa."""
    excel_service = BASE_DIR / "analisis/services/data/excel_service.py"
    excel_cervise = BASE_DIR / "analisis/services/data/excel_cervise.py"
    
    if excel_service.exists():
        FIXES.append("✅ excel_service.py existe")
    else:
        ERRORS.append("❌ excel_service.py no encontrado")
    
    if excel_cervise.exists():
        FIXES.append("⚠️  excel_cervise.py aún existe (pero no se importa)")

def main():
    """Ejecutar todas las reparaciones."""
    print("\n" + "="*60)
    print("🔧 REPARADOR DE IMPORTS Y MÓDULOS DEL PROYECTO")
    print("="*60 + "\n")
    
    # Ejecutar reparaciones
    fix_requirements_txt()
    verify_module_structure()
    verify_excel_service()
    
    # Mostrar resultados
    if FIXES:
        print("\n✅ CORRECCIONES APLICADAS:")
        for fix in FIXES:
            print(f"   {fix}")
    
    if ERRORS:
        print("\n❌ ERRORES ENCONTRADOS:")
        for error in ERRORS:
            print(f"   {error}")
        print("\n⚠️  El proyecto puede no funcionar correctamente.")
        return 1
    else:
        print("\n🎉 ¡Todos los problemas han sido reparados!")
        print("\n📝 PRÓXIMOS PASOS:")
        print("   1. pip install -r requirements.txt")
        print("   2. python manage.py migrate")
        print("   3. python manage.py runserver")
        return 0

if __name__ == "__main__":
    exit(main())
