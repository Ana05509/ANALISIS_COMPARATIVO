#!/usr/bin/env python
"""Script para detectar errores de imports en todo el proyecto."""

import os
import sys
import traceback

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

errors = []

# Importar Django y setup
try:
    import django
    django.setup()
    print("✓ Django setup completado")
except Exception as e:
    print(f"✗ Error en setup de Django: {e}")
    traceback.print_exc()
    errors.append(("Django setup", str(e)))

# Importar modelos
try:
    from analisis.models import *
    print("✓ Modelos importados correctamente")
except Exception as e:
    print(f"✗ Error importando modelos: {e}")
    traceback.print_exc()
    errors.append(("Modelos", str(e)))

# Importar servicios
try:
    from analisis.services.business import (
        upload_service,
        comparison_service,
        analysis_service,
        visualization_service,
        statistics_service,
        report_service,
        export_service,
        catalog_service,
    )
    print("✓ Servicios business importados")
except Exception as e:
    print(f"✗ Error importando servicios business: {e}")
    traceback.print_exc()
    errors.append(("Servicios business", str(e)))

# Importar servicios de processing
try:
    from analisis.services.processing import (
        pipeline,
        taxonomy,
        cleaning,
        abundance,
        analytics,
        diversity,
    )
    print("✓ Servicios processing importados")
except Exception as e:
    print(f"✗ Error importando servicios processing: {e}")
    traceback.print_exc()
    errors.append(("Servicios processing", str(e)))

# Importar servicios de interpretation
try:
    from analisis.services.interpretation import (
        microorganism_classifier,
        beneficial_service,
        pathogen_service,
    )
    print("✓ Servicios interpretation importados")
except Exception as e:
    print(f"✗ Error importando servicios interpretation: {e}")
    traceback.print_exc()
    errors.append(("Servicios interpretation", str(e)))

# Importar servicios de data
try:
    from analisis.services.data import (
        file_service,
        metadata_service,
    )
    print("✓ Servicios data importados")
except Exception as e:
    print(f"✗ Error importando servicios data: {e}")
    traceback.print_exc()
    errors.append(("Servicios data", str(e)))

# Importar views
try:
    from analisis.views import (
        dashboard,
        subir_datos,
        comparar,
        historial,
        ver_producto,
        analisis_avanzado,
        catalogo_microorganismos,
        detalle_microorganismo,
        actualizar_clasificacion,
        reportes,
        generar_reporte,
        detalle_reporte,
    )
    print("✓ Views importadas correctamente")
except Exception as e:
    print(f"✗ Error importando views: {e}")
    traceback.print_exc()
    errors.append(("Views", str(e)))

# Resumen
print("\n" + "="*60)
if errors:
    print(f"❌ Se encontraron {len(errors)} errores de importación:")
    for modulo, error in errors:
        print(f"\n  {modulo}:")
        print(f"    {error}")
    sys.exit(1)
else:
    print("✅ Todos los imports están correctos")
    sys.exit(0)
