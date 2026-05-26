#!/usr/bin/env python
# run_phase3_tests.py
"""
Script para ejecutar y validar Phase 3 (Testing y Validación)
"""

import os
import sys
import django
from django.conf import settings
from django.test.utils import get_runner

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()
    
    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=2, interactive=True, keepdb=False)
    
    print("\n" + "="*70)
    print("🧪 PHASE 3: TESTING Y VALIDACIÓN COMPLETA".center(70))
    print("="*70 + "\n")
    
    # Ejecutar tests
    print("▶️  Ejecutando suite de tests...\n")
    failures = test_runner.run_tests(["analisis.tests"])
    
    print("\n" + "="*70)
    if failures == 0:
        print("✅ TODOS LOS TESTS PASARON EXITOSAMENTE".center(70))
    else:
        print(f"❌ {failures} TEST(S) FALLARON".center(70))
    print("="*70 + "\n")
    
    sys.exit(bool(failures))
