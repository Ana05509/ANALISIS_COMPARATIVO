#!/usr/bin/env python3
"""
Script para crear estructura de directorios y archivos necesarios
"""

import os
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).parent

def crear_estructura():
    """Crea la estructura de directorios necesaria"""
    
    # Directorios a crear
    directorios = [
        BASE_DIR / 'templates',
        BASE_DIR / 'templates' / 'analisis',
        BASE_DIR / 'static',
        BASE_DIR / 'static' / 'css',
        BASE_DIR / 'static' / 'js',
        BASE_DIR / 'static' / 'images',
        BASE_DIR / 'media',
        BASE_DIR / 'media' / 'archivos',
    ]
    
    print("📁 Creando directorios...")
    for directorio in directorios:
        directorio.mkdir(parents=True, exist_ok=True)
        print(f"   ✓ {directorio.relative_to(BASE_DIR)}")
    
    # Crear archivo CSS
    css_file = BASE_DIR / 'static' / 'css' / 'style.css'
    if not css_file.exists():
        # Copiar desde static_style.css
        src = BASE_DIR / 'analisis' / 'static_style.css'
        if src.exists():
            shutil.copy(src, css_file)
            print(f"   ✓ Copiado CSS")
    
    # Crear templates
    base_template = BASE_DIR / 'templates' / 'base.html'
    if not base_template.exists():
        src = BASE_DIR / 'analisis' / 'templates_base.html'
        if src.exists():
            shutil.copy(src, base_template)
            print(f"   ✓ Template base creado")
    
    print("✅ Estructura creada exitosamente")

def crear_templates_vistas():
    """Crea templates para las vistas principales"""
    
    templates_dir = BASE_DIR / 'templates' / 'analisis'
    
    # Template para dashboard
    dashboard_template = templates_dir / 'dashboard.html'
    if not dashboard_template.exists():
        with open(dashboard_template, 'w', encoding='utf-8') as f:
            f.write('''{% extends "base.html" %}

{% block title %}Dashboard - Análisis Microbianos{% endblock %}

{% block content %}
<h1>Dashboard</h1>
<div class="card">
    <h2>Bienvenido al Sistema de Análisis Microbianos</h2>
    <p>Selecciona una opción del menú para comenzar.</p>
    <ul>
        <li><a href="{% url 'analisis:subir_datos' %}">Subir nuevos datos</a></li>
        <li><a href="{% url 'analisis:comparar' %}">Comparar muestras</a></li>
        <li><a href="{% url 'analisis:catalogo' %}">Ver catálogo</a></li>
    </ul>
</div>
{% endblock %}
''')
    
    print("✓ Dashboard template creado")
    
    # Crear templates mínimas para otras vistas
    vistas = [
        ('subir_datos.html', 'Subir Datos'),
        ('comparar.html', 'Comparar Muestras'),
        ('catalogo_microorganismos.html', 'Catálogo de Microorganismos'),
        ('reportes.html', 'Reportes'),
        ('historial.html', 'Historial'),
    ]
    
    for nombre, titulo in vistas:
        path = templates_dir / nombre
        if not path.exists():
            with open(path, 'w', encoding='utf-8') as f:
                f.write(f'''{% extends "base.html" %}}

{{% block title %}}{titulo} - Análisis Microbianos{{% endblock %}}

{{% block content %}}
<h1>{titulo}</h1>
<div class="card">
    <p>Contenido de {titulo}.</p>
</div>
{{% endblock %}}
''')
            print(f"✓ {nombre} creado")

if __name__ == '__main__':
    print("\n🚀 CREADOR DE ESTRUCTURA DE DIRECTORIOS\n")
    crear_estructura()
    crear_templates_vistas()
    print("\n✅ ¡Estructura lista para usar!\n")
