import os
import ast
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ============================================================
# CONFIGURACIÓN AUTOMÁTICA DE RUTAS (Estructura Real)
# ============================================================

# Toma como base el directorio donde se encuentra este script (Raíz del proyecto)
BASE_DIR = Path(__file__).resolve().parent

PROJECT_PATH = str(BASE_DIR)
OUTPUT_FILE = os.path.join(PROJECT_PATH, "analisis_proyecto.md")

VALID_EXTENSIONS = [".py"]

# ============================================================
# CLASIFICADOR SEMÁNTICO ADAPTADO A TERRABIOLAB
# ============================================================

CATEGORY_RULES = {
    "Modelos y Persistencia (Base de Datos)": [
        "models.model", "foreignkey", "charfield", "integerfield", 
        "datetimefield", "db_table", "migrations"
    ],
    "Controladores de Interfaz (Vistas/Views)": [
        "views", "request", "render", "redirect", "get_object_or_404", 
        "httpresponse", "login_required"
    ],
    "Servicios de Negocio (Business Services)": [
        "analysis_service", "catalog_service", "comparison_service",
        "export_service", "report_service", "statistics_service"
    ],
    "Procesamiento Algorítmico y Bioinformática": [
        "abundance", "analytics", "diversity", "pipeline", "taxonomy",
        "cleaning", "pandas", "numpy", "dataframe", "16s", "its"
    ],
    "Servicios de Datos e Interpretación": [
        "excel_service", "file_service", "metadata_service",
        "beneficial_service", "microorganism_classifier", "pathogen_service"
    ],
    "Administración Personalizada (Unfold)": [
        "admin.register", "modeladmin", "unfold.admin", "list_display", 
        "list_filter", "unfold_fix"
    ],
    "Formularios de Usuario (Forms)": [
        "forms.modelform", "forms.form", "cleaned_data", "widgets"
    ],
    "Enrutamiento del Sistema (URLs)": [
        "urlpatterns", "path", "include", "reverse_lazy"
    ],
    "Ecosistema de Pruebas Automatizadas (Tests)": [
        "test_", "testcase", "pytest", "assertcontains", "coverage"
    ]
}

# ============================================================
# FUNCIONES DE EXTRACCIÓN SINTÁCTICA (AST)
# ============================================================

def detect_category(file_path: str, content: str) -> str:
    # Primero valida por nombres clave en las rutas de tu estructura real
    path_lower = file_path.lower()
    if "services/processing" in path_lower:
        return "Procesamiento Algorítmico y Bioinformática"
    if "services/business" in path_lower:
        return "Servicios de Negocio (Business Services)"
    if "services/interpretation" in path_lower:
        return "Servicios de Datos e Interpretación"
    if "views" in path_lower:
        return "Controladores de Interfaz (Vistas/Views)"
    if "test" in path_lower or "tests.py" in path_lower:
        return "Ecosistema de Pruebas Automatizadas (Tests)"

    # Clasificación heurística complementaria basada en el contenido
    scores = defaultdict(int)
    lower_content = content.lower()

    for category, keywords in CATEGORY_RULES.items():
        for keyword in keywords:
            if keyword in lower_content:
                scores[category] += 1

    # Heurística corregida con Lambda para evitar quejas de tipado en Pylance
    if scores and max(scores.values()) > 0:
        return max(scores, key=lambda k: scores[k])

    return "Configuración / Infraestructura Core"


def analyze_python_file(file_path: str):
    result = {
        "functions": [],
        "classes": [],
        "imports": [],
        "category": "Desconocida",
        "description": "",
    }

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()

        tree = ast.parse(content)
        result["category"] = detect_category(file_path, content)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                result["functions"].append(node.name)
            elif isinstance(node, ast.ClassDef):
                result["classes"].append(node.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    result["imports"].append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    result["imports"].append(node.module)

        result["description"] = generate_description(result)

    except Exception as e:
        result["description"] = f"Aviso de lectura: {e}"

    return result


def generate_description(data: dict) -> str:
    desc = [f"Módulo enfocado en **{data['category']}**."]
    if data["classes"]:
        desc.append(f"Define {len(data['classes'])} estructuras de objeto/clase.")
    if data["functions"]:
        desc.append(f"Implementa {len(data['functions'])} funciones lógicas.")
    return " ".join(desc)


def analyze_project(project_path: str):
    project_data = {}
    
    # Directorios excluidos del conteo para agilizar el análisis estático
    ignored_dirs = [
        "__pycache__", ".git", "venv", "env", ".venv", 
        "node_modules", "static", "staticfiles", "media", "data"
    ]

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in ignored_dirs]

        for file in files:
            ext = os.path.splitext(file)[1]
            if ext in VALID_EXTENSIONS:
                full_path = os.path.join(root, file)
                relative_path = os.path.relpath(full_path, project_path)

                # Evita registrar archivos de reparación/testeo sueltos de la raíz
                if relative_path.startswith("repair_") or relative_path.startswith("test_"):
                    if root == project_path: 
                        continue

                print(f"🕵️‍♂️ Analizando: {relative_path}")
                analysis = analyze_python_file(full_path)
                project_data[relative_path] = analysis

    return project_data


def generate_markdown(project_path: str, project_data: dict) -> str:
    lines = [
        "# 🔬 REPORTE ESTRUCTURAL DE ARQUITECTURA: TERRABIOLAB",
        f"**Fecha de Análisis:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Directorio Raíz:** `{project_path}`\n",
        "---",
        "## 📊 MÉTRICAS GENERALES DEL PROYECTO\n",
        f"**Módulos de Código Python Analizados:** {len(project_data)}\n",
        "### Componentes del Ecosistema Detectados:"
    ]

    categories = defaultdict(int)
    for data in project_data.values():
        categories[data["category"]] += 1

    for cat, total in categories.items():
        lines.append(f"- **{cat}:** {total} archivo(s) estructurado(s)")

    lines.extend(["\n---", "## 📂 DESGLOSE TÉCNICO POR MÓDULO\n"])

    for path, data in project_data.items():
        lines.append(f"### 📄 `{path}`\n")
        lines.append(f"- **Capa de Software:** {data['category']}")
        lines.append(f"- **Resumen Estático:** {data['description']}\n")

        if data["classes"]:
            lines.append("  **Estructuras de Clases:**")
            for cls in data["classes"]:
                lines.append(f"  - `{cls}`")
        
        if data["functions"]:
            lines.append("  **Funciones de Procesamiento:**")
            for func in data["functions"]:
                lines.append(f"  - `{func}()`")

        if data["imports"]:
            lines.append("  **Módulos / Dependencias Relacionadas:**")
            unique_imports = list(set(data["imports"]))
            lines.append(f"  - `[{', '.join(unique_imports[:7])}]`")

        lines.append("\n" + "—"*30 + "\n")

    return "\n".join(lines)


# ============================================================
# EJECUCIÓN DEL PROCESO
# ============================================================

if __name__ == "__main__":
    print("\n" + "="*50)
    print("      ANALIZADOR DE COMPONENTES BIOINFORMÁTICOS       ")
    print("              SISTEMA: TERRABIOLAB                    ")
    print("="*50 + "\n")

    if not os.path.exists(PROJECT_PATH):
        print(f"Error: No se puede acceder al directorio del proyecto.")
        exit()

    analysis_results = analyze_project(PROJECT_PATH)
    markdown_report = generate_markdown(PROJECT_PATH, analysis_results)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as output:
        output.write(markdown_report)

    print("\n" + "="*50)
    print("  DOCUMENTACIÓN INTEGRAL GENERADA CON ÉXITO ")
    print("="*50)
    print(f"Reporte listo para revisión en: {OUTPUT_FILE}\n")